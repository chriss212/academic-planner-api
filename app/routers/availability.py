from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.models.availability import AvailabilityBlock
from app.schemas.availability import AvailabilityCreate, AvailabilityOut

router = APIRouter(prefix="/availability", tags=["availability"])

TEMP_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

@router.post("/", response_model=AvailabilityOut, status_code=201)
async def create_block(payload: AvailabilityCreate, db: AsyncSession = Depends(get_db)):
    block = AvailabilityBlock(**payload.model_dump(), user_id=TEMP_USER_ID)
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block

@router.get("/", response_model=list[AvailabilityOut])
async def list_blocks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AvailabilityBlock)
        .where(AvailabilityBlock.user_id == TEMP_USER_ID)
        .order_by(AvailabilityBlock.block_date, AvailabilityBlock.start_time)
    )
    return result.scalars().all()

@router.delete("/{block_id}", status_code=204)
async def delete_block(block_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AvailabilityBlock).where(AvailabilityBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    await db.delete(block)
    await db.commit()