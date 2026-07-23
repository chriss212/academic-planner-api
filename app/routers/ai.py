from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.database import get_db
from app.models.ai_trace import AITrace
from app.schemas.ai_trace import AITraceOut
from app.schemas.cost import CostEstimateOut
from app.schemas.plan import PlanGenerationRequest, PlanGenerationResponse
from app.services.cost import estimate_cost
from app.services.replanning import generate_and_persist_plan

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/plans/generate", response_model=PlanGenerationResponse)
async def generate_plan(
	payload: PlanGenerationRequest,
	db: AsyncSession = Depends(get_db),
	user_id = Depends(get_current_user_id),
):
	return await generate_and_persist_plan(db, user_id, payload)


@router.get("/cost", response_model=CostEstimateOut)
async def get_cost_estimate(
	monthly_plans: int | None = Query(
		default=None,
		ge=0,
		description="Nº de planificaciones esperadas al mes para proyectar el gasto mensual.",
	),
	db: AsyncSession = Depends(get_db),
	user_id = Depends(get_current_user_id),
):
	"""Estimación de coste operativo del agente a partir de los tokens trazados."""
	return await estimate_cost(db, user_id, monthly_plans=monthly_plans)


@router.get("/traces", response_model=list[AITraceOut])
async def list_ai_traces(
	db: AsyncSession = Depends(get_db),
	user_id = Depends(get_current_user_id),
):
	"""Historial de trazas de IA del usuario, incluyendo intentos fallidos (RF-09/10)."""
	result = await db.execute(
		select(AITrace).where(AITrace.user_id == user_id).order_by(AITrace.created_at.desc())
	)
	return result.scalars().all()
