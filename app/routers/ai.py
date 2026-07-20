from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.database import get_db
from app.schemas.plan import PlanGenerationRequest, PlanGenerationResponse
from app.services.replanning import generate_and_persist_plan

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/plans/generate", response_model=PlanGenerationResponse)
async def generate_plan(
	payload: PlanGenerationRequest,
	db: AsyncSession = Depends(get_db),
	user_id = Depends(get_current_user_id),
):
	return await generate_and_persist_plan(db, user_id, payload)