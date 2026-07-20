from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HistoryEntryOut(BaseModel):
    id: UUID
    plan_id: UUID
    version: int
    scope: str
    action: str
    approval_status: str
    prompt_used: str
    created_at: Optional[datetime]
    user_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)