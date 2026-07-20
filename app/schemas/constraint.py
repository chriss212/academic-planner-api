from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from typing import Optional, Any
from enum import Enum

class ConstraintType(str, Enum):
    blocked_time      = "blocked_time"
    max_session_hours = "max_session_hours"
    fixed_task        = "fixed_task"
    academic_priority = "academic_priority"

class ConstraintCreate(BaseModel):
    type:        ConstraintType
    description: str
    metadata:    Optional[dict[str, Any]] = None

class ConstraintUpdate(BaseModel):
    type:        Optional[ConstraintType] = None
    description: Optional[str] = None
    metadata:    Optional[dict[str, Any]] = None

class ConstraintOut(BaseModel):
    id:          UUID
    user_id:     UUID
    type:        ConstraintType
    description: str
    metadata:    Optional[dict[str, Any]] = Field(default=None, alias="meta_data")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)