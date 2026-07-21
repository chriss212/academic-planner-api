from __future__ import annotations

from datetime import date, datetime
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
from app.schemas.task import TaskOut, TaskStatus
from app.services.planning import analyze_planning_input, build_planning_context
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
    task_outs = [_task_out(task) for task in tasks]
    availability_outs = [_availability_out(block) for block in availability_blocks]
    constraint_outs = [_constraint_out(constraint) for constraint in constraints]

    analysis = analyze_planning_input(task_outs, availability_outs, constraint_outs)
    if not analysis.is_ready:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ERR-DATA-001",
                "message": f"Faltan datos para generar el plan: {', '.join(analysis.missing)}.",
                "missing": analysis.missing,
            },
        )

    today = date.today()
    for task in tasks:
        if task.deadline < today and task.status not in ("completed", "overdue"):
            task.status = TaskStatus.overdue.value
    task_outs = [_task_out(task) for task in tasks]

    previous_plan = await _latest_plan(db, user_id)
    scope = payload.scope or (previous_plan.scope if previous_plan else "semanal")
    version = (previous_plan.version + 1) if previous_plan else 1

    context = build_planning_context(
        tasks=task_outs,
        availability_blocks=availability_outs,
        constraints=constraint_outs,
        scope=scope,
        user_note=payload.user_note,
        previous_plan={
            "id": str(previous_plan.id),
            "version": previous_plan.version,
            "scope": previous_plan.scope,
            "plan": previous_plan.plan,
            "viabilidad": previous_plan.viabilidad,
            "justificacion": previous_plan.justificacion,
        }
        if previous_plan
        else None,
        analysis=analysis,
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
        tasks=task_outs,
        availability_blocks=availability_outs,
        constraints=constraint_outs,
    )

    response_status = "valid" if business_validation.is_valid else "invalid"
    estado_revision = "normal" if business_validation.is_valid else "requiere_revision"

    if business_validation.is_valid:
        viabilidad = parsed.viabilidad
    else:
        viabilidad = business_validation.forced_viabilidad or "no_viable"

    riesgos = list(dict.fromkeys([*analysis.warnings, *business_validation.riesgos, *list(parsed.riesgos)]))
    recomendaciones = list(
        dict.fromkeys(
            [*analysis.recommendations, *business_validation.recomendaciones, *list(parsed.recomendaciones)]
        )
    )
    conflictos = (
        [c.model_dump(mode="json") for c in business_validation.conflictos]
        if business_validation.conflictos
        else [c.model_dump(mode="json") for c in parsed.conflictos]
    )

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
                status=task.status if task else "programada",
            )
        )

    plan_row = Plan(
        user_id=user_id,
        version=version,
        version_plan=f"v{version}",
        scope=scope,
        viabilidad=viabilidad,
        justificacion=parsed.justificacion,
        riesgos=riesgos,
        conflictos=conflictos,
        recomendaciones=recomendaciones,
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