from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut

router = APIRouter(prefix="/tasks", tags=["tasks"])

# UUID fijo por ahora — cuando tengan auth esto viene del token
TEMP_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

@router.post("/", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(**payload.model_dump(), user_id=TEMP_USER_ID)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task

@router.get("/", response_model=list[TaskOut])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(Task.user_id == TEMP_USER_ID).order_by(Task.deadline)
    )
    return result.scalars().all()

@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return task

@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: UUID, payload: TaskUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    return task

@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    await db.delete(task)
    await db.commit()