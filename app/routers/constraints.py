from fastapi import APIRouter, Depends, HTTPException, Response
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
from app.services.replanning import try_auto_replan
from app.schemas.plan import PlanGenerationRequest

router = APIRouter(prefix="/constraints", tags=["constraints"])

@router.post("/", response_model=ConstraintOut, status_code=201)
async def create_constraint(
    payload: ConstraintCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    constraint = Constraint(
        type=payload.type,
        description=payload.description,
        meta_data=payload.metadata,
        user_id=user_id,
    )
    db.add(constraint)
    await db.commit()
    await db.refresh(constraint)
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por cambio de restricción",
            change_block={
                "tipo_evento": "restriccion_cambiada",
                "entity": "constraint",
                "operation": "create",
                "constraint_id": str(constraint.id),
                "changes": payload.model_dump(mode="json"),
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status
    # El replan puede haber hecho rollback (p. ej. tras una colisión de versión
    # por concurrencia), lo que invalida los objetos ya cargados en la sesión.
    await db.refresh(constraint)
    return constraint

@router.get("/", response_model=list[ConstraintOut])
async def list_constraints(db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(select(Constraint).where(Constraint.user_id == user_id))
    return result.scalars().all()

@router.patch("/{constraint_id}", response_model=ConstraintOut)
async def update_constraint(
    constraint_id: UUID,
    payload: ConstraintUpdate,
    response: Response,
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
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por actualización de restricción",
            change_block={
                "tipo_evento": "restriccion_cambiada",
                "entity": "constraint",
                "operation": "update",
                "constraint_id": str(constraint_id),
                "changes": payload.model_dump(exclude_none=True, mode="json"),
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status
    await db.refresh(constraint)
    return constraint

@router.delete("/{constraint_id}", status_code=204)
async def delete_constraint(
    constraint_id: UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(Constraint).where(Constraint.id == constraint_id, Constraint.user_id == user_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Restricción no encontrada")
    snapshot = ConstraintOut.model_validate(c).model_dump(mode="json")
    await db.delete(c)
    await db.commit()
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por eliminación de restricción",
            change_block={
                "tipo_evento": "restriccion_cambiada",
                "entity": "constraint",
                "operation": "delete",
                "constraint_id": str(constraint_id),
                "snapshot": snapshot,
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status