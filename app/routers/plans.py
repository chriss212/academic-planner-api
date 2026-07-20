from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.auth import get_current_user_id
from app.database import get_db
from app.models.history import HistoryEntry
from app.models.plan import Plan
from app.schemas.history import HistoryEntryOut
from app.schemas.plan import PlanApprovalUpdate, PlanGenerationResponse, PlanItemOut, PlanManualUpdate

router = APIRouter(prefix="/plans", tags=["plans"])


def _to_response(plan: Plan) -> PlanGenerationResponse:
    return PlanGenerationResponse(
        id=plan.id,
        version=plan.version,
        version_plan=plan.version_plan,
        scope=plan.scope,
        generated_at=plan.created_at,
        approval_status=plan.approval_status,
        viabilidad=plan.viabilidad,
        plan=[PlanItemOut.model_validate(item) for item in (plan.plan or [])],
        justificacion=plan.justificacion,
        riesgos=list(plan.riesgos or []),
        conflictos=list(plan.conflictos or []),
        recomendaciones=list(plan.recomendaciones or []),
        prompt_enviado=plan.prompt_enviado,
        respuesta_ia=plan.respuesta_ia,
        response_status=plan.response_status,
        modelo_usado=plan.modelo_usado,
        validation_code=plan.validation_code,
        estado_revision=plan.estado_revision,
    )


@router.get("/", response_model=list[PlanGenerationResponse])
async def list_plans(db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(select(Plan).where(Plan.user_id == user_id).order_by(Plan.version.desc()))
    return [_to_response(plan) for plan in result.scalars().all()]


@router.get("/latest", response_model=PlanGenerationResponse)
async def get_latest_plan(db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(
        select(Plan).where(Plan.user_id == user_id).order_by(Plan.version.desc()).limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No hay plan generado")
    return _to_response(plan)


@router.get("/history", response_model=list[HistoryEntryOut])
async def list_history(db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(
        select(HistoryEntry).where(HistoryEntry.user_id == user_id).order_by(HistoryEntry.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{plan_id}", response_model=PlanGenerationResponse)
async def get_plan(plan_id: UUID, db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(select(Plan).where(Plan.id == plan_id, Plan.user_id == user_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    return _to_response(plan)


@router.patch("/{plan_id}", response_model=PlanGenerationResponse)
async def update_plan(
    plan_id: UUID,
    payload: PlanManualUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(Plan).where(Plan.id == plan_id, Plan.user_id == user_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    plan.plan = [item.model_dump(mode="json") for item in payload.plan]
    plan.approval_status = "editado"
    plan.estado_revision = "normal"
    if payload.user_note:
        plan.justificacion = f"{plan.justificacion}\n\nNota del usuario: {payload.user_note}"

    history = HistoryEntry(
        user_id=user_id,
        plan_id=plan.id,
        version=plan.version,
        scope=plan.scope,
        action="editado",
        approval_status="editado",
        prompt_used=plan.prompt_enviado,
        user_note=payload.user_note,
    )
    db.add(history)
    await db.commit()
    await db.refresh(plan)
    return _to_response(plan)


@router.patch("/{plan_id}/approval", response_model=PlanGenerationResponse)
async def update_approval(
    plan_id: UUID,
    payload: PlanApprovalUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(Plan).where(Plan.id == plan_id, Plan.user_id == user_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    plan.approval_status = payload.approval_status
    history = HistoryEntry(
        user_id=user_id,
        plan_id=plan.id,
        version=plan.version,
        scope=plan.scope,
        action=payload.approval_status,
        approval_status=payload.approval_status,
        prompt_used=plan.prompt_enviado,
        user_note=payload.user_note,
    )
    db.add(history)
    await db.commit()
    await db.refresh(plan)
    return _to_response(plan)