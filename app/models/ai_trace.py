from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class AITrace(Base):
    __tablename__ = "ai_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    version = Column(Integer, nullable=False)
    prompt_enviado = Column(Text, nullable=False)
    respuesta_ia = Column(Text, nullable=False)
    response_status = Column(String(20), nullable=False)
    modelo_usado = Column(String(100), nullable=False)
    tokens_entrada = Column(Integer)
    tokens_salida = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())