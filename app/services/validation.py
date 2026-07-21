"""Validación de reglas de negocio sobre un plan generado o editado

Cubre RF-08 / RNF-04:
- tarea inexistente
- fuera de disponibilidad
- blocked_time
- fixed_task (posición exacta o choque)
- max_session_hours
- solapes entre sesiones del propio plan
- sesión después del deadline
- esfuerzo insuficiente (minutos planificados < effort)
- sobrecarga por día (ERR-PLAN-001)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time
from uuid import UUID

from app.schemas.availability import AvailabilityOut
from app.schemas.constraint import ConstraintOut, ConstraintType
from app.schemas.plan import PlanItemOut, PlanConflictOut
from app.schemas.task import TaskOut


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
class BusinessValidationResult:
    is_valid: bool
    validation_code: str | None = None
    conflictos: list[PlanConflictOut] = field(default_factory=list)
    riesgos: list[str] = field(default_factory=list)
    recomendaciones: list[str] = field(default_factory=list)
    deficit_minutes: int = 0
    forced_viabilidad: str | None = None


def _time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and end_a > start_b


def _parse_time(value: object) -> time | None:
    try:
        return time.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _extract_constraints(
    constraints: list[ConstraintOut],
) -> tuple[int | None, list[ConstraintOut], list[ConstraintOut]]:
    max_session_minutes: int | None = None
    fixed_blocks: list[ConstraintOut] = []
    blocked_times: list[ConstraintOut] = []

    for constraint in constraints:
        metadata = constraint.metadata or {}
        if constraint.type == ConstraintType.max_session_hours:
            if isinstance(metadata.get("max_session_minutes"), (int, float)):
                max_session_minutes = int(metadata["max_session_minutes"])
            elif isinstance(metadata.get("max_session_hours"), (int, float)):
                max_session_minutes = int(float(metadata["max_session_hours"]) * 60)
        elif constraint.type == ConstraintType.fixed_task:
            fixed_blocks.append(constraint)
        elif constraint.type == ConstraintType.blocked_time:
            blocked_times.append(constraint)

    return max_session_minutes, fixed_blocks, blocked_times


def _blocked_matches(item: PlanItemOut, constraint: ConstraintOut) -> bool:
    metadata = constraint.metadata or {}
    constraint_date = metadata.get("date")
    constraint_weekday = metadata.get("weekday")
    matches_date = constraint_date and str(constraint_date) == item.dia.isoformat()
    matches_weekday = (
        constraint_weekday and str(constraint_weekday) == WEEKDAY_NAMES[item.dia.weekday()]
    )
    if not (matches_date or matches_weekday):
        return False

    start = _parse_time(metadata.get("start_time"))
    end = _parse_time(metadata.get("end_time"))
    if not (start and end):
        return False

    return _overlaps(
        _time_to_minutes(item.bloque_inicio),
        _time_to_minutes(item.bloque_fin),
        _time_to_minutes(start),
        _time_to_minutes(end),
    )


def _fixed_task_window(constraint: ConstraintOut) -> tuple[UUID | None, date | None, time | None, time | None]:
    metadata = constraint.metadata or {}
    task_id_raw = metadata.get("task_id")
    try:
        task_id = UUID(str(task_id_raw)) if task_id_raw else None
    except ValueError:
        task_id = None
    return (
        task_id,
        _parse_date(metadata.get("date") or metadata.get("dia")),
        _parse_time(metadata.get("start_time") or metadata.get("bloque_inicio")),
        _parse_time(metadata.get("end_time") or metadata.get("bloque_fin")),
    )


def validate_plan_business_rules(
    plan_items: list[PlanItemOut],
    tasks: list[TaskOut],
    availability_blocks: list[AvailabilityOut],
    constraints: list[ConstraintOut],
) -> BusinessValidationResult:
    conflicts: list[PlanConflictOut] = []
    risks: list[str] = []
    recommendations: list[str] = []
    deficit_minutes = 0

    task_by_id = {str(task.id): task for task in tasks}
    availability_by_day: dict[date, list[AvailabilityOut]] = {}
    for block in availability_blocks:
        availability_by_day.setdefault(block.date, []).append(block)

    max_session_minutes, fixed_blocks, blocked_times = _extract_constraints(constraints)

    for item in plan_items:
        task = task_by_id.get(str(item.tarea_id))
        if task is None:
            conflicts.append(
                PlanConflictOut(
                    tarea_id=item.tarea_id,
                    tipo="tarea_inexistente",
                    severidad="critico",
                    mensaje=f"La tarea {item.tarea_id} no existe en el contexto enviado.",
                )
            )
            continue

        start_minutes = _time_to_minutes(item.bloque_inicio)
        end_minutes = _time_to_minutes(item.bloque_fin)
        duration = end_minutes - start_minutes

        if item.dia > task.deadline:
            conflicts.append(
                PlanConflictOut(
                    tarea_id=item.tarea_id,
                    tipo="despues_del_deadline",
                    severidad="critico",
                    mensaje=(
                        f"La sesión queda el {item.dia.isoformat()}, "
                        f"después del deadline {task.deadline.isoformat()}."
                    ),
                )
            )
            risks.append(f"fecha_limite_en_riesgo:{task.id}")

        if max_session_minutes and duration > max_session_minutes:
            conflicts.append(
                PlanConflictOut(
                    tarea_id=item.tarea_id,
                    tipo="excede_duracion_maxima",
                    severidad="advertencia",
                    mensaje=(
                        f"La sesión dura {duration} min y el máximo permitido es "
                        f"{max_session_minutes} min."
                    ),
                )
            )
            recommendations.append("Divide la tarea en sesiones más cortas.")

        day_blocks = availability_by_day.get(item.dia, [])
        if not day_blocks:
            conflicts.append(
                PlanConflictOut(
                    tarea_id=item.tarea_id,
                    tipo="sin_disponibilidad",
                    severidad="critico",
                    mensaje=f"No hay disponibilidad declarada para {item.dia.isoformat()}.",
                )
            )
            deficit_minutes += duration
        else:
            within_any_block = False
            for block in day_blocks:
                block_start = _time_to_minutes(block.start_time)
                block_end = _time_to_minutes(block.end_time)
                if start_minutes >= block_start and end_minutes <= block_end:
                    within_any_block = True
                    break
            if not within_any_block:
                conflicts.append(
                    PlanConflictOut(
                        tarea_id=item.tarea_id,
                        tipo="fuera_de_disponibilidad",
                        severidad="critico",
                        mensaje="El bloque propuesto no cae dentro de la disponibilidad declarada.",
                    )
                )
                deficit_minutes += duration

        for constraint in blocked_times:
            if _blocked_matches(item, constraint):
                conflicts.append(
                    PlanConflictOut(
                        tarea_id=item.tarea_id,
                        tipo="blocked_time",
                        severidad="critico",
                        mensaje=f"La sesión cae en un horario bloqueado: {constraint.description}.",
                    )
                )

        for constraint in fixed_blocks:
            fixed_task_id, fixed_date, fixed_start, fixed_end = _fixed_task_window(constraint)
            if not (fixed_date and fixed_start and fixed_end):
                continue

            if fixed_task_id and item.tarea_id == fixed_task_id:
                if (
                    item.dia != fixed_date
                    or item.bloque_inicio != fixed_start
                    or item.bloque_fin != fixed_end
                ):
                    conflicts.append(
                        PlanConflictOut(
                            tarea_id=item.tarea_id,
                            tipo="restriccion_violada",
                            severidad="critico",
                            mensaje=(
                                "La tarea fija no quedó en su ventana declarada "
                                f"({fixed_date.isoformat()} {fixed_start.isoformat(timespec='minutes')}-"
                                f"{fixed_end.isoformat(timespec='minutes')})."
                            ),
                        )
                    )
                continue

            if item.dia != fixed_date:
                continue
            if _overlaps(
                start_minutes,
                end_minutes,
                _time_to_minutes(fixed_start),
                _time_to_minutes(fixed_end),
            ):
                conflicts.append(
                    PlanConflictOut(
                        tarea_id=item.tarea_id,
                        tipo="choque_con_tarea_fija",
                        severidad="critico",
                        mensaje="El plan entra en conflicto con una tarea fija o bloque ocupado.",
                    )
                )

    items_by_day: dict[date, list[PlanItemOut]] = defaultdict(list)
    for item in plan_items:
        items_by_day[item.dia].append(item)

    for day, day_items in items_by_day.items():
        ordered = sorted(day_items, key=lambda i: (i.bloque_inicio, i.bloque_fin))
        for index, current in enumerate(ordered):
            current_start = _time_to_minutes(current.bloque_inicio)
            current_end = _time_to_minutes(current.bloque_fin)
            for other in ordered[index + 1 :]:
                other_start = _time_to_minutes(other.bloque_inicio)
                other_end = _time_to_minutes(other.bloque_fin)
                if not _overlaps(current_start, current_end, other_start, other_end):
                    break
                conflicts.append(
                    PlanConflictOut(
                        tarea_id=current.tarea_id,
                        tipo="solape_entre_sesiones",
                        severidad="critico",
                        mensaje=(
                            f"Solape el {day.isoformat()} entre "
                            f"{current.bloque_inicio.isoformat(timespec='minutes')}-"
                            f"{current.bloque_fin.isoformat(timespec='minutes')} y "
                            f"{other.bloque_inicio.isoformat(timespec='minutes')}-"
                            f"{other.bloque_fin.isoformat(timespec='minutes')}."
                        ),
                    )
                )

    planned_minutes: dict[str, int] = defaultdict(int)
    for item in plan_items:
        planned_minutes[str(item.tarea_id)] += _time_to_minutes(item.bloque_fin) - _time_to_minutes(
            item.bloque_inicio
        )

    for task in tasks:
        if task.status.value == "completed":
            continue
        needed = task.effort_hours * 60
        planned = planned_minutes.get(str(task.id), 0)
        if planned == 0:
            conflicts.append(
                PlanConflictOut(
                    tarea_id=task.id,
                    tipo="tarea_sin_tiempo",
                    severidad="advertencia",
                    mensaje=f"La tarea '{task.title}' no tiene ninguna sesión asignada.",
                )
            )
            recommendations.append(f"Asigna tiempo a '{task.title}' o ajusta su esfuerzo.")
            deficit_minutes += needed
        elif planned < needed:
            shortfall = needed - planned
            conflicts.append(
                PlanConflictOut(
                    tarea_id=task.id,
                    tipo="esfuerzo_insuficiente",
                    severidad="advertencia",
                    mensaje=(
                        f"La tarea '{task.title}' necesita {needed} min y solo tiene "
                        f"{planned} min planificados (faltan {shortfall})."
                    ),
                )
            )
            risks.append(f"fecha_limite_en_riesgo:{task.id}")
            deficit_minutes += shortfall

    available_by_day: dict[date, int] = defaultdict(int)
    for block in availability_blocks:
        available_by_day[block.date] += _time_to_minutes(block.end_time) - _time_to_minutes(
            block.start_time
        )

    tasks_assigned_by_day: dict[date, set[str]] = defaultdict(set)
    for item in plan_items:
        tasks_assigned_by_day[item.dia].add(str(item.tarea_id))

    for day, task_ids in tasks_assigned_by_day.items():
        required = sum(
            task_by_id[tid].effort_hours * 60
            for tid in task_ids
            if tid in task_by_id
        )
        available = available_by_day.get(day, 0)
        if required > available:
            day_deficit = required - available
            deficit_minutes += day_deficit
            conflicts.append(
                PlanConflictOut(
                    tarea_id=None,
                    tipo="sobrecarga",
                    severidad="critico",
                    mensaje=(
                        f"Sobrecarga el {day.isoformat()}: las tareas asignadas requieren "
                        f"{required} min y solo hay {available} min disponibles "
                        f"(déficit {day_deficit})."
                    ),
                )
            )

    if not conflicts:
        return BusinessValidationResult(is_valid=True)

    has_overload = any(c.tipo == "sobrecarga" for c in conflicts)
    has_hard_violation = any(
        c.tipo
        in {
            "fuera_de_disponibilidad",
            "blocked_time",
            "restriccion_violada",
            "choque_con_tarea_fija",
            "despues_del_deadline",
            "solape_entre_sesiones",
            "tarea_inexistente",
            "sin_disponibilidad",
        }
        for c in conflicts
    )

    if has_overload and not has_hard_violation:
        code = "ERR-PLAN-001"
        forced = "no_viable"
        risks = risks or ["Hay más trabajo del que cabe en la disponibilidad declarada."]
        recommendations = recommendations or [
            "Ajusta fechas, reduce alcance o agrega disponibilidad."
        ]
    else:
        code = "ERR-IA-004"
        forced = "no_viable" if has_hard_violation else "viable_con_ajustes"
        risks = risks or ["El plan necesita ajustes antes de aprobarse."]
        recommendations = recommendations or ["Reubica los bloques conflictivos."]

    return BusinessValidationResult(
        is_valid=False,
        validation_code=code,
        conflictos=conflicts,
        riesgos=risks,
        recomendaciones=recommendations,
        deficit_minutes=deficit_minutes,
        forced_viabilidad=forced,
    )
