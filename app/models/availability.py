import uuid
from sqlalchemy import Column, String, Time, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class AvailabilityBlock(Base):
    __tablename__ = "availability_blocks"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), nullable=False)
    day        = Column(String(20), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time   = Column(Time, nullable=False)
    label      = Column(String(100))

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="chk_time_order"),
        CheckConstraint(
            "day IN ('lunes','martes','miercoles','jueves','viernes','sabado','domingo')",
            name="chk_availability_day",
        ),
    )