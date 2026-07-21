from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.models.constraint import Constraint
from app.schemas.constraint import (
    ConstraintCreate,
    ConstraintOut,
    ConstraintUpdate,
    validate_constraint_metadata,
)
from app.core.auth import get_current_user_id
from app.services.replanning import generate_and_persist_plan
from app.schemas.plan import PlanGenerationRequest

router = APIRouter(prefix="/constraints", tags=["constraints"])

@router.post("/", response_model=ConstraintOut, status_code=201)
async def create_constraint(payload: ConstraintCreate, db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    constraint = Constraint(
        type=payload.type,
        description=payload.description,
        meta_data=payload.metadata,
        user_id=user_id,
    )
    db.add(constraint)
    await db.commit()
    await db.refresh(constraint)
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por cambio de restricción",
                change_block={
                    "entity": "constraint",
                    "operation": "create",
                    "constraint_id": str(constraint.id),
                    "changes": payload.model_dump(mode="json"),
                },
            ),
        )
    except HTTPException:
        pass
    return constraint

@router.get("/", response_model=list[ConstraintOut])
async def list_constraints(db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(select(Constraint).where(Constraint.user_id == user_id))
    return result.scalars().all()

@router.patch("/{constraint_id}", response_model=ConstraintOut)
async def update_constraint(
    constraint_id: UUID,
    payload: ConstraintUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(Constraint).where(Constraint.id == constraint_id, Constraint.user_id == user_id))
    constraint = result.scalar_one_or_none()
    if not constraint:
        raise HTTPException(status_code=404, detail="Restricción no encontrada")

    changes = payload.model_dump(exclude_none=True)
    if "metadata" in changes and payload.type is None:
        try:
            changes["metadata"] = validate_constraint_metadata(constraint.type, changes["metadata"])
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    if "metadata" in changes:
        constraint.meta_data = changes.pop("metadata")
    for field, value in changes.items():
        setattr(constraint, field, value)
    await db.commit()
    await db.refresh(constraint)
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por actualización de restricción",
                change_block={
                    "entity": "constraint",
                    "operation": "update",
                    "constraint_id": str(constraint_id),
                    "changes": payload.model_dump(exclude_none=True, mode="json"),
                },
            ),
        )
    except HTTPException:
        pass
    return constraint

@router.delete("/{constraint_id}", status_code=204)
async def delete_constraint(constraint_id: UUID, db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(select(Constraint).where(Constraint.id == constraint_id, Constraint.user_id == user_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Restricción no encontrada")
    await db.delete(c)
    await db.commit()
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por eliminación de restricción",
                change_block={
                    "entity": "constraint",
                    "operation": "delete",
                    "constraint_id": str(c.id),
                    "snapshot": ConstraintOut.model_validate(c).model_dump(mode="json"),
                },
            ),
        )
    except HTTPException:
        pass