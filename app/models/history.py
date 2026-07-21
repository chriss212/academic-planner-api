from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.database import Base


class HistoryEntry(Base):
    __tablename__ = "history_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    scope = Column(String(20), nullable=False)
    action = Column(String(30), nullable=False)
    approval_status = Column(String(30), nullable=False)
    prompt_used = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    user_note = Column(Text)
    change_block = Column(JSONB)