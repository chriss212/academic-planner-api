from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AITraceOut(BaseModel):
    id: UUID
    plan_id: Optional[UUID] = None
    version: int
    prompt_enviado: str
    respuesta_ia: str
    response_status: str
    modelo_usado: str
    tokens_entrada: Optional[int] = None
    tokens_salida: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
