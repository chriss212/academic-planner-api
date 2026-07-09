import uuid
from sqlalchemy import Column, String, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base

class Constraint(Base):
    __tablename__ = "constraints"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), nullable=False)
    type        = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    meta_data    = Column(JSONB)

    __table_args__ = (
        CheckConstraint(
            "type IN ('blocked_time','max_session_hours','fixed_task','academic_priority')",
            name="chk_constraint_type"
        ),
    )