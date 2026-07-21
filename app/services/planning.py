"""Reglas de negocio previas a la llamada de IA

Se ejecutan sobre los datos crudos del usuario para:
1. Detectar datos insuficientes (ERR-DATA-001).
2. Marcar tareas vencidas como overdue.
3. Calcular capacidad vs esfuerzo y deadlines en riesgo.
4. Inyectar advertencias en el contexto que se envía al modelo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time

from app.schemas.availability import AvailabilityOut
from app.schemas.constraint import ConstraintOut, ConstraintType
from app.schemas.task import TaskOut, TaskStatus


WEEKDAY_NAMES = {
    0: "lunes",
    1: "martes",
    2: "miercoles",
    3: "jueves",
    4: "viernes",
    5: "sabado",
    6: "domingo",
}


@dataclass(slots=True)
class PrePlanningAnalysis:
    """Resultado del análisis previo a la generación con IA."""

    is_ready: bool
    missing: list[str] = field(default_factory=list)
    total_effort_minutes: int = 0
    total_available_minutes: int = 0
    deficit_minutes: int = 0
    overload: bool = False
    overdue_task_ids: list[str] = field(default_factory=list)
    deadlines_at_risk: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def _time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _block_duration_minutes(block: AvailabilityOut) -> int:
    return _time_to_minutes(block.end_time) - _time_to_minutes(block.start_time)


def _blocked_minutes_for_date(
    day: date,
    constraints: list[ConstraintOut],
) -> int:
    """Minutos bloqueados que restan capacidad del día (blocked_time)."""
    total = 0
    weekday = WEEKDAY_NAMES[day.weekday()]
    for constraint in constraints:
        if constraint.type != ConstraintType.blocked_time:
            continue
        metadata = constraint.metadata or {}
        constraint_date = metadata.get("date")
        constraint_weekday = metadata.get("weekday")
        matches_date = constraint_date and str(constraint_date) == day.isoformat()
        matches_weekday = constraint_weekday and str(constraint_weekday) == weekday
        if not (matches_date or matches_weekday):
            continue
        start = metadata.get("start_time")
        end = metadata.get("end_time")
        if not (start and end):
            continue
        try:
            start_m = _time_to_minutes(time.fromisoformat(str(start)))
            end_m = _time_to_minutes(time.fromisoformat(str(end)))
        except ValueError:
            continue
        if end_m > start_m:
            total += end_m - start_m
    return total


def analyze_planning_input(
    tasks: list[TaskOut],
    availability_blocks: list[AvailabilityOut],
    constraints: list[ConstraintOut],
    today: date | None = None,
) -> PrePlanningAnalysis:
    """Analiza datos del usuario antes de llamar a la IA."""
    today = today or date.today()
    missing: list[str] = []
    if not tasks:
        missing.append("tareas")
    if not availability_blocks:
        missing.append("bloques de disponibilidad")
    if missing:
        return PrePlanningAnalysis(is_ready=False, missing=missing)

    active_statuses = {TaskStatus.pending, TaskStatus.in_progress, TaskStatus.overdue, TaskStatus.rescheduled}
    active_tasks = [task for task in tasks if task.status in active_statuses]
    if not active_tasks:
        return PrePlanningAnalysis(
            is_ready=False,
            missing=["tareas activas (pending/in_progress/overdue/rescheduled)"],
        )

    overdue_ids = [
        str(task.id)
        for task in active_tasks
        if task.deadline < today and task.status != TaskStatus.completed
    ]

    total_effort = sum(task.effort_hours * 60 for task in active_tasks)
    available_by_date: dict[date, int] = {}
    for block in availability_blocks:
        available_by_date[block.date] = available_by_date.get(block.date, 0) + _block_duration_minutes(block)

    total_available = 0
    for day, minutes in available_by_date.items():
        effective = max(0, minutes - _blocked_minutes_for_date(day, constraints))
        available_by_date[day] = effective
        total_available += effective

    deficit = max(0, total_effort - total_available)
    overload = total_effort > total_available

    deadlines_at_risk: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if overdue_ids:
        warnings.append(
            f"{len(overdue_ids)} tarea(s) ya vencida(s); deben priorizarse o marcarse como overdue."
        )
        recommendations.append("Actualiza deadlines o reduce el alcance de las tareas vencidas.")

    if overload:
        warnings.append(
            f"Sobrecarga detectada: se necesitan {total_effort} min y solo hay "
            f"{total_available} min disponibles (déficit {deficit} min)."
        )
        recommendations.append(
            "Reduce el alcance, mueve deadlines o agrega más bloques de disponibilidad."
        )

    cumulative_capacity_before: dict[str, int] = {}
    for task in active_tasks:
        capacity_before_deadline = sum(
            minutes for day, minutes in available_by_date.items() if day <= task.deadline
        )
        cumulative_capacity_before[str(task.id)] = capacity_before_deadline
        needed = task.effort_hours * 60
        if capacity_before_deadline < needed:
            deadlines_at_risk.append(str(task.id))
            warnings.append(
                f"Tarea '{task.title}' ({task.id}) tiene riesgo de no cumplir su deadline "
                f"({task.deadline.isoformat()}): necesita {needed} min y hay "
                f"{capacity_before_deadline} min antes de esa fecha."
            )

    for task in active_tasks:
        if task.effort_hours > 8:
            warnings.append(
                f"Tarea '{task.title}' estima {task.effort_hours} h; considera dividirla en sesiones."
            )

    return PrePlanningAnalysis(
        is_ready=True,
        total_effort_minutes=total_effort,
        total_available_minutes=total_available,
        deficit_minutes=deficit,
        overload=overload,
        overdue_task_ids=overdue_ids,
        deadlines_at_risk=deadlines_at_risk,
        warnings=warnings,
        recommendations=recommendations,
    )


def build_planning_context(
    tasks: list[TaskOut],
    availability_blocks: list[AvailabilityOut],
    constraints: list[ConstraintOut],
    scope: str,
    user_note: str | None = None,
    previous_plan: dict[str, object] | None = None,
    analysis: PrePlanningAnalysis | None = None,
) -> dict[str, object]:
    """Arma el contexto estructurado que se envía al modelo."""
    active_statuses = {TaskStatus.pending, TaskStatus.in_progress, TaskStatus.overdue, TaskStatus.rescheduled}
    planning_tasks = [task for task in tasks if task.status in active_statuses]

    context: dict[str, object] = {
        "scope": scope,
        "user_note": user_note,
        "previous_plan": previous_plan,
        "fecha_generacion": date.today().isoformat(),
        "tasks": [
            {
                "id": str(task.id),
                "title": task.title,
                "description": task.description,
                "category": task.category,
                "deadline": task.deadline.isoformat(),
                "priority": task.priority,
                "effort_estimado_min": task.effort_hours * 60,
                "status": task.status.value,
            }
            for task in planning_tasks
        ],
        "availability_blocks": [
            {
                "id": str(block.id),
                "date": block.date.isoformat(),
                "start_time": block.start_time.isoformat(timespec="minutes"),
                "end_time": block.end_time.isoformat(timespec="minutes"),
                "label": block.label,
            }
            for block in availability_blocks
        ],
        "constraints": [
            {
                "id": str(constraint.id),
                "type": constraint.type.value,
                "description": constraint.description,
                "metadata": constraint.metadata,
            }
            for constraint in constraints
        ],
    }

    if analysis is not None:
        context["analisis_previo"] = {
            "total_effort_minutes": analysis.total_effort_minutes,
            "total_available_minutes": analysis.total_available_minutes,
            "deficit_minutes": analysis.deficit_minutes,
            "overload": analysis.overload,
            "overdue_task_ids": analysis.overdue_task_ids,
            "deadlines_at_risk": analysis.deadlines_at_risk,
            "warnings": analysis.warnings,
            "recommendations": analysis.recommendations,
        }

    return context


def summarize_tasks(tasks: list[TaskOut]) -> dict[str, object]:
    total_effort = sum(task.effort_hours for task in tasks)
    imminent_deadline = min((task.deadline for task in tasks), default=None)
    return {
        "total_tasks": len(tasks),
        "total_effort_hours": total_effort,
        "nearest_deadline": imminent_deadline.isoformat() if imminent_deadline else None,
    }
