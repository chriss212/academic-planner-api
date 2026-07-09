from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.models.constraint import Constraint
from app.schemas.constraint import ConstraintCreate, ConstraintOut

router = APIRouter(prefix="/constraints", tags=["constraints"])

TEMP_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

@router.post("/", response_model=ConstraintOut, status_code=201)
async def create_constraint(payload: ConstraintCreate, db: AsyncSession = Depends(get_db)):
    constraint = Constraint(**payload.model_dump(), user_id=TEMP_USER_ID)
    db.add(constraint)
    await db.commit()
    await db.refresh(constraint)
    return constraint

@router.get("/", response_model=list[ConstraintOut])
async def list_constraints(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Constraint).where(Constraint.user_id == TEMP_USER_ID)
    )
    return result.scalars().all()

@router.delete("/{constraint_id}", status_code=204)
async def delete_constraint(constraint_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Constraint).where(Constraint.id == constraint_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Restricción no encontrada")
    await db.delete(c)
    await db.commit()