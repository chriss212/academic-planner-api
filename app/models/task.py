import uuid
from sqlalchemy import Column, String, Integer, Date, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(UUID(as_uuid=True), nullable=False)
    title        = Column(String(255), nullable=False)
    description  = Column(Text)
    category     = Column(String(100))
    deadline     = Column(Date, nullable=False)
    priority     = Column(Integer, nullable=False)
    effort_hours = Column(Integer, nullable=False)
    status       = Column(String(50), nullable=False, default="pending")
    created_at   = Column(DateTime, server_default=func.now())
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 5", name="chk_priority"),
        CheckConstraint("effort_hours > 0", name="chk_effort"),
        CheckConstraint(
            "status IN ('pending','in_progress','completed','overdue','rescheduled')",
            name="chk_status"
        ),
    )