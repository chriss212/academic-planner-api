from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ia.ia_client import IAClientError
from app.ia.replan_service import ReplanService
from app.models.ai_trace import AITrace
from app.models.history import HistoryEntry
from app.models.plan import Plan
from app.models.availability import AvailabilityBlock
from app.models.constraint import Constraint
from app.models.task import Task
from app.schemas.availability import AvailabilityOut
from app.schemas.constraint import ConstraintOut
from app.schemas.plan import PlanGenerationRequest, PlanGenerationResponse, PlanItemOut, PlanConflictOut
from app.schemas.task import TaskOut
from app.services.planning import build_planning_context
from app.services.validation import validate_plan_business_rules


def _task_out(task: Task) -> TaskOut:
    return TaskOut.model_validate(task)


def _availability_out(block: AvailabilityBlock) -> AvailabilityOut:
    return AvailabilityOut.model_validate(block)


def _constraint_out(constraint: Constraint) -> ConstraintOut:
    return ConstraintOut.model_validate(constraint)


async def _load_context(db: AsyncSession, user_id: UUID):
    tasks_result = await db.execute(select(Task).where(Task.user_id == user_id).order_by(Task.deadline))
    availability_result = await db.execute(
        select(AvailabilityBlock).where(AvailabilityBlock.user_id == user_id).order_by(AvailabilityBlock.date)
    )
    constraint_result = await db.execute(select(Constraint).where(Constraint.user_id == user_id))

    tasks = tasks_result.scalars().all()
    availability_blocks = availability_result.scalars().all()
    constraints = constraint_result.scalars().all()
    return tasks, availability_blocks, constraints


async def _latest_plan(db: AsyncSession, user_id: UUID) -> Plan | None:
    result = await db.execute(
        select(Plan)
        .where(Plan.user_id == user_id)
        .order_by(Plan.version.desc(), Plan.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _plan_to_response(plan: Plan) -> PlanGenerationResponse:
    return PlanGenerationResponse(
        id=plan.id,
        version=plan.version,
        version_plan=plan.version_plan,
        scope=plan.scope,
        generated_at=plan.created_at or datetime.utcnow(),
        approval_status=plan.approval_status,
        viabilidad=plan.viabilidad,
        plan=[PlanItemOut.model_validate(item) for item in plan.plan],
        justificacion=plan.justificacion,
        riesgos=list(plan.riesgos or []),
        conflictos=[PlanConflictOut.model_validate(item) for item in (plan.conflictos or [])],
        recomendaciones=list(plan.recomendaciones or []),
        prompt_enviado=plan.prompt_enviado,
        respuesta_ia=plan.respuesta_ia,
        response_status=plan.response_status,
        modelo_usado=plan.modelo_usado,
        validation_code=plan.validation_code,
        estado_revision=plan.estado_revision,
    )


async def generate_and_persist_plan(
    db: AsyncSession,
    user_id: UUID,
    payload: PlanGenerationRequest,
) -> PlanGenerationResponse:
    tasks, availability_blocks, constraints = await _load_context(db, user_id)

    if not tasks or not availability_blocks:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ERR-DATA-001",
                "message": "Faltan tareas o bloques de disponibilidad para generar el plan.",
            },
        )

    previous_plan = await _latest_plan(db, user_id)
    scope = payload.scope or (previous_plan.scope if previous_plan else "semanal")
    version = (previous_plan.version + 1) if previous_plan else 1

    context = build_planning_context(
        tasks=[_task_out(task) for task in tasks],
        availability_blocks=[_availability_out(block) for block in availability_blocks],
        constraints=[_constraint_out(constraint) for constraint in constraints],
        scope=scope,
        user_note=payload.user_note,
        previous_plan={
            "id": str(previous_plan.id),
            "version": previous_plan.version,
            "scope": previous_plan.scope,
        }
        if previous_plan
        else None,
    )

    service = ReplanService()
    try:
        raw_response, parsed, prompt_used, token_usage = await service.generate_plan(
            payload=PlanGenerationRequest(scope=scope, user_note=payload.user_note, change_block=payload.change_block),
            context=context,
            task_ids=[task.id for task in tasks],
        )
    except IAClientError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "ERR-SYS-001", "message": "Servicio de IA no disponible"},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail={"code": "ERR-IA-001", "message": str(error)},
        ) from error

    business_validation = validate_plan_business_rules(
        plan_items=[PlanItemOut.model_validate(item) for item in parsed.plan],
        tasks=[_task_out(task) for task in tasks],
        availability_blocks=[_availability_out(block) for block in availability_blocks],
        constraints=[_constraint_out(constraint) for constraint in constraints],
    )

    response_status = "valid" if business_validation.is_valid else "invalid"
    estado_revision = "normal" if business_validation.is_valid else "requiere_revision"

    task_lookup = {str(task.id): task for task in tasks}
    enriched_plan = []
    for item in parsed.plan:
        task = task_lookup.get(str(item.tarea_id))
        enriched_plan.append(
            PlanItemOut(
                tarea_id=item.tarea_id,
                dia=item.dia,
                bloque_inicio=item.bloque_inicio,
                bloque_fin=item.bloque_fin,
                orden=item.orden,
                task_title=task.title if task else None,
                priority=task.priority if task else None,
                status="programada" if not task else task.status.value,
            )
        )

    plan_row = Plan(
        user_id=user_id,
        version=version,
        version_plan=f"v{version}",
        scope=scope,
        viabilidad=parsed.viabilidad if business_validation.is_valid else "no_viable",
        justificacion=parsed.justificacion,
        riesgos=business_validation.riesgos or list(parsed.riesgos),
        conflictos=[conflict.model_dump(mode="json") for conflict in (business_validation.conflictos or parsed.conflictos)],
        recomendaciones=business_validation.recomendaciones or list(parsed.recomendaciones),
        plan=[item.model_dump(mode="json") for item in enriched_plan],
        prompt_enviado=prompt_used,
        respuesta_ia=raw_response,
        response_status=response_status,
        modelo_usado=settings.openai_model,
        validation_code=business_validation.validation_code,
        estado_revision=estado_revision,
        approval_status="propuesto",
    )
    db.add(plan_row)
    await db.flush()

    history_entry = HistoryEntry(
        user_id=user_id,
        plan_id=plan_row.id,
        version=version,
        scope=scope,
        action="replanificado" if previous_plan else "generado",
        approval_status="propuesto",
        prompt_used=plan_row.prompt_enviado,
        user_note=payload.user_note,
    )
    db.add(history_entry)

    trace = AITrace(
        user_id=user_id,
        plan_id=plan_row.id,
        version=version,
        prompt_enviado=prompt_used,
        respuesta_ia=raw_response,
        response_status=response_status,
        modelo_usado=settings.openai_model,
        tokens_entrada=token_usage.input_tokens,
        tokens_salida=token_usage.output_tokens,
    )
    db.add(trace)

    await db.commit()
    await db.refresh(plan_row)
    return _plan_to_response(plan_row)