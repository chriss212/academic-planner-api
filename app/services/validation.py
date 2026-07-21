from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time

from app.schemas.availability import AvailabilityOut
from app.schemas.constraint import ConstraintOut, ConstraintType
from app.schemas.plan import PlanItemOut, PlanConflictOut
from app.schemas.task import TaskOut


@dataclass(slots=True)
class BusinessValidationResult:
    is_valid: bool
    validation_code: str | None = None
    conflictos: list[PlanConflictOut] = field(default_factory=list)
    riesgos: list[str] = field(default_factory=list)
    recomendaciones: list[str] = field(default_factory=list)
    deficit_minutes: int = 0


def _time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and end_a > start_b


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

    max_session_minutes = None
    fixed_blocks: list[ConstraintOut] = []

    for constraint in constraints:
        if constraint.type == ConstraintType.max_session_hours:
            metadata = constraint.metadata or {}
            if isinstance(metadata.get("max_session_minutes"), (int, float)):
                max_session_minutes = int(metadata["max_session_minutes"])
            elif isinstance(metadata.get("max_session_hours"), (int, float)):
                max_session_minutes = int(float(metadata["max_session_hours"]) * 60)
        elif constraint.type == ConstraintType.fixed_task:
            fixed_blocks.append(constraint)

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

        if max_session_minutes and duration > max_session_minutes:
            conflicts.append(
                PlanConflictOut(
                    tarea_id=item.tarea_id,
                    tipo="sesion_excede_limite",
                    severidad="advertencia",
                    mensaje="La sesión propuesta supera el máximo permitido por la restricción declarada.",
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
            continue

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

        for constraint in fixed_blocks:
            metadata = constraint.metadata or {}
            # La tarea fija puede ocupar su propia ventana sin generar conflicto.
            if metadata.get("task_id") and str(item.tarea_id) == str(metadata["task_id"]):
                continue
            constraint_day = metadata.get("date") or metadata.get("dia")
            constraint_start = metadata.get("start_time") or metadata.get("bloque_inicio")
            constraint_end = metadata.get("end_time") or metadata.get("bloque_fin")
            if not (constraint_day and constraint_start and constraint_end):
                continue
            try:
                constraint_date = date.fromisoformat(str(constraint_day))
            except ValueError:
                continue
            if constraint_date != item.dia:
                continue
            fixed_start = _time_to_minutes(time.fromisoformat(str(constraint_start)))
            fixed_end = _time_to_minutes(time.fromisoformat(str(constraint_end)))
            if _overlaps(start_minutes, end_minutes, fixed_start, fixed_end):
                conflicts.append(
                    PlanConflictOut(
                        tarea_id=item.tarea_id,
                        tipo="choque_con_tarea_fija",
                        severidad="critico",
                        mensaje="El plan entra en conflicto con una tarea fija o bloque ocupado.",
                    )
                )

    if conflicts:
        return BusinessValidationResult(
            is_valid=False,
            validation_code="ERR-IA-004",
            conflictos=conflicts,
            riesgos=["El plan necesita ajustes antes de aprobarse."],
            recomendaciones=recommendations or ["Reubica los bloques conflictivos."],
            deficit_minutes=deficit_minutes,
        )

    return BusinessValidationResult(is_valid=True)