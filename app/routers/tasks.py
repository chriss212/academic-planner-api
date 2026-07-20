from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut
from app.core.auth import get_current_user_id
from app.services.replanning import generate_and_persist_plan
from app.schemas.plan import PlanGenerationRequest

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    task = Task(**payload.model_dump(), user_id=user_id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por creación de tarea",
                change_block={
                    "entity": "task",
                    "operation": "create",
                    "task_id": str(task.id),
                    "changes": payload.model_dump(mode="json"),
                },
            ),
        )
    except HTTPException:
        pass
    return task

@router.get("/", response_model=list[TaskOut])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(
        select(Task).where(Task.user_id == user_id).order_by(Task.deadline)
    )
    return result.scalars().all()

@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return task

@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por actualización de tarea",
                change_block={
                    "entity": "task",
                    "operation": "update",
                    "task_id": str(task.id),
                    "changes": payload.model_dump(exclude_none=True, mode="json"),
                },
            ),
        )
    except HTTPException:
        pass
    return task

@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    await db.delete(task)
    await db.commit()
    try:
        await generate_and_persist_plan(
            db,
            user_id,
            PlanGenerationRequest(
                scope="semanal",
                user_note="Replanificación por eliminación de tarea",
                change_block={
                    "entity": "task",
                    "operation": "delete",
                    "task_id": str(task.id),
                    "snapshot": TaskOut.model_validate(task).model_dump(mode="json"),
                },
            ),
        )
    except HTTPException:
        pass