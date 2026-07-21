from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from uuid import UUID
from app.database import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskStatus, TaskSummaryOut, TaskUpdate, TaskOut
from app.core.auth import get_current_user_id
from app.services.replanning import try_auto_replan
from app.schemas.plan import PlanGenerationRequest

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    task = Task(**payload.model_dump(), user_id=user_id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por creación de tarea",
            change_block={
                "tipo_evento": "tarea_nueva",
                "entity": "task",
                "operation": "create",
                "task_id": str(task.id),
                "changes": payload.model_dump(mode="json"),
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status
    return task

@router.get("/", response_model=list[TaskOut])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    query = select(Task).where(Task.user_id == user_id).order_by(Task.deadline)
    if status is not None:
        query = query.where(Task.status == status.value)
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/summary", response_model=TaskSummaryOut)
async def task_summary(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Panel de seguimiento (RF-11): conteo de tareas por estado."""
    result = await db.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.user_id == user_id)
        .group_by(Task.status)
    )
    counts = {status: count for status, count in result.all()}
    return TaskSummaryOut(
        total=sum(counts.values()),
        pending=counts.get("pending", 0),
        in_progress=counts.get("in_progress", 0),
        completed=counts.get("completed", 0),
        overdue=counts.get("overdue", 0),
        rescheduled=counts.get("rescheduled", 0),
    )

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
    response: Response,
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
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por actualización de tarea",
            change_block={
                "tipo_evento": "tarea_modificada",
                "entity": "task",
                "operation": "update",
                "task_id": str(task.id),
                "changes": payload.model_dump(exclude_none=True, mode="json"),
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status
    return task

@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    snapshot = TaskOut.model_validate(task).model_dump(mode="json")
    await db.delete(task)
    await db.commit()
    replan_status = await try_auto_replan(
        db,
        user_id,
        PlanGenerationRequest(
            scope="semanal",
            user_note="Replanificación por eliminación de tarea",
            change_block={
                "tipo_evento": "tarea_modificada",
                "entity": "task",
                "operation": "delete",
                "task_id": str(task_id),
                "snapshot": snapshot,
            },
        ),
    )
    response.headers["X-Replan-Status"] = replan_status
