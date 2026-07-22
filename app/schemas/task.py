from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import date, datetime
from uuid import UUID
from typing import Optional
from enum import Enum

class TaskStatus(str, Enum):
    pending     = "pending"
    in_progress = "in_progress"
    completed   = "completed"
    overdue     = "overdue"
    rescheduled = "rescheduled"

class TaskCreate(BaseModel):
    title:        str            = Field(..., min_length=1, max_length=255)
    description:  Optional[str] = None
    category:     Optional[str] = None
    deadline:     date
    priority:     int            = Field(..., ge=1, le=5)
    effort_hours: int            = Field(..., gt=0)

    @field_validator("deadline")
    @classmethod
    def deadline_not_past(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("deadline no puede ser anterior a hoy")
        return value

class TaskUpdate(BaseModel):
    title:        Optional[str]        = None
    description:  Optional[str]        = None
    category:     Optional[str]        = None
    deadline:     Optional[date]       = None
    priority:     Optional[int]        = Field(None, ge=1, le=5)
    effort_hours: Optional[int]        = Field(None, gt=0)
    status:       Optional[TaskStatus] = None

    # A diferencia de TaskCreate, aquí NO se valida que deadline no sea pasado:
    # una tarea existente cuya fecha límite ya venció (p. ej. una tarea atrasada)
    # debe poder seguir editándose — cambiar su estado, reprogramarla, etc. —
    # sin que ese chequeo bloquee la actualización.

class TaskSummaryOut(BaseModel):
    total:       int
    pending:     int
    in_progress: int
    completed:   int
    overdue:     int
    rescheduled: int

class TaskOut(BaseModel):
    id:           UUID
    user_id:      UUID
    title:        str
    description:  Optional[str]
    category:     Optional[str]
    deadline:     date
    priority:     int
    effort_hours: int
    status:       TaskStatus
    created_at:   Optional[datetime]

    model_config = ConfigDict(from_attributes=True)