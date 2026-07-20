from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.models.availability import AvailabilityBlock
from app.schemas.availability import AvailabilityCreate, AvailabilityOut, AvailabilityUpdate
from app.core.auth import get_current_user_id
from app.services.replanning import generate_and_persist_plan
from app.schemas.plan import PlanGenerationRequest

router = APIRouter(prefix="/availability", tags=["availability"])

@router.post("/", response_model=AvailabilityOut, status_code=201)
async def create_block(
    payload: AvailabilityCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    block = AvailabilityBlock(**payload.model_dump(), user_id=user_id)
    db.add(block)
    await db.commit()
    await db.refresh(block)
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por cambio de disponibilidad",
                change_block={
                    "entity": "availability",
                    "operation": "create",
                    "block_id": str(block.id),
                    "changes": payload.model_dump(mode="json"),
                },
            ),
        )
    except HTTPException:
        pass
    return block

@router.get("/", response_model=list[AvailabilityOut])
async def list_blocks(db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(
        select(AvailabilityBlock)
        .where(AvailabilityBlock.user_id == user_id)
        .order_by(AvailabilityBlock.day, AvailabilityBlock.start_time)
    )
    return result.scalars().all()

@router.patch("/{block_id}", response_model=AvailabilityOut)
async def update_block(
    block_id: UUID,
    payload: AvailabilityUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(AvailabilityBlock).where(AvailabilityBlock.id == block_id, AvailabilityBlock.user_id == user_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(block, field, value)
    await db.commit()
    await db.refresh(block)
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por actualización de disponibilidad",
                change_block={
                    "entity": "availability",
                    "operation": "update",
                    "block_id": str(block_id),
                    "changes": payload.model_dump(exclude_none=True, mode="json"),
                },
            ),
        )
    except HTTPException:
        pass
    return block

@router.delete("/{block_id}", status_code=204)
async def delete_block(block_id: UUID, db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(select(AvailabilityBlock).where(AvailabilityBlock.id == block_id, AvailabilityBlock.user_id == user_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    await db.delete(block)
    await db.commit()
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por eliminación de disponibilidad",
                change_block={
                    "entity": "availability",
                    "operation": "delete",
                    "block_id": str(block.id),
                    "snapshot": AvailabilityOut.model_validate(block).model_dump(mode="json"),
                },
            ),
        )
    except HTTPException:
        pass