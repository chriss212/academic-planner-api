from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    version = Column(Integer, nullable=False)
    version_plan = Column(String(50), nullable=False)
    scope = Column(String(20), nullable=False)
    viabilidad = Column(String(50), nullable=False)
    justificacion = Column(Text, nullable=False)
    riesgos = Column(JSONB, nullable=False, default=list)
    conflictos = Column(JSONB, nullable=False, default=list)
    recomendaciones = Column(JSONB, nullable=False, default=list)
    plan = Column(JSONB, nullable=False, default=list)
    prompt_enviado = Column(Text, nullable=False)
    respuesta_ia = Column(Text, nullable=False)
    response_status = Column(String(20), nullable=False)
    modelo_usado = Column(String(100), nullable=False)
    validation_code = Column(String(50))
    estado_revision = Column(String(30), nullable=False, default="normal")
    approval_status = Column(String(30), nullable=False, default="propuesto")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())