from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.models.availability import AvailabilityBlock
from app.schemas.availability import AvailabilityCreate, AvailabilityOut, AvailabilityUpdate
from app.core.auth import get_current_user_id
from app.services.replanning import try_auto_replan
from app.schemas.plan import PlanGenerationRequest

router = APIRouter(prefix="/availability", tags=["availability"])


async def _check_no_overlap(
    db: AsyncSession,
    user_id: UUID,
    day,
    start_time,
    end_time,
    exclude_id: UUID | None = None,
) -> None:
    query = select(AvailabilityBlock).where(
        AvailabilityBlock.user_id == user_id,
        AvailabilityBlock.date == day,
        AvailabilityBlock.start_time < end_time,
        AvailabilityBlock.end_time > start_time,
    )
    if exclude_id is not None:
        query = query.where(AvailabilityBlock.id != exclude_id)
    result = await db.execute(query.limit(1))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ERR-DATA-002",
                "message": f"El bloque se solapa con otro ya registrado el {day.isoformat()}.",
            },
        )


@router.post("/", response_model=AvailabilityOut, status_code=201)
async def create_block(
    payload: AvailabilityCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    await _check_no_overlap(db, user_id, payload.date, payload.start_time, payload.end_time)
    block = AvailabilityBlock(**payload.model_dump(), user_id=user_id)
    db.add(block)
    await db.commit()
    await db.refresh(block)
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por cambio de disponibilidad",
            change_block={
                "tipo_evento": "disponibilidad_cambiada",
                "entity": "availability",
                "operation": "create",
                "block_id": str(block.id),
                "changes": payload.model_dump(mode="json"),
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status
    # El replan puede haber hecho rollback (p. ej. tras una colisión de versión
    # por concurrencia), lo que invalida los objetos ya cargados en la sesión.
    await db.refresh(block)
    return block

@router.get("/", response_model=list[AvailabilityOut])
async def list_blocks(db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(
        select(AvailabilityBlock)
        .where(AvailabilityBlock.user_id == user_id)
        .order_by(AvailabilityBlock.date, AvailabilityBlock.start_time)
    )
    return result.scalars().all()

@router.patch("/{block_id}", response_model=AvailabilityOut)
async def update_block(
    block_id: UUID,
    payload: AvailabilityUpdate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(AvailabilityBlock).where(AvailabilityBlock.id == block_id, AvailabilityBlock.user_id == user_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")

    changes = payload.model_dump(exclude_none=True)
    new_date = changes.get("date", block.date)
    new_start = changes.get("start_time", block.start_time)
    new_end = changes.get("end_time", block.end_time)
    if new_end <= new_start:
        raise HTTPException(
            status_code=422,
            detail={"code": "ERR-DATA-002", "message": "end_time debe ser mayor que start_time."},
        )
    await _check_no_overlap(db, user_id, new_date, new_start, new_end, exclude_id=block_id)

    for field, value in changes.items():
        setattr(block, field, value)
    await db.commit()
    await db.refresh(block)
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por actualización de disponibilidad",
            change_block={
                "tipo_evento": "disponibilidad_cambiada",
                "entity": "availability",
                "operation": "update",
                "block_id": str(block_id),
                "changes": payload.model_dump(exclude_none=True, mode="json"),
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status
    await db.refresh(block)
    return block

@router.delete("/{block_id}", status_code=204)
async def delete_block(
    block_id: UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(AvailabilityBlock).where(AvailabilityBlock.id == block_id, AvailabilityBlock.user_id == user_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    snapshot = AvailabilityOut.model_validate(block).model_dump(mode="json")
    await db.delete(block)
    await db.commit()
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por eliminación de disponibilidad",
            change_block={
                "tipo_evento": "disponibilidad_cambiada",
                "entity": "availability",
                "operation": "delete",
                "block_id": str(block_id),
                "snapshot": snapshot,
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status