from __future__ import annotations

import json
import re
from datetime import time
from typing import Iterable, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.schemas.availability import Weekday


class ClaudePlanItem(BaseModel):
    tarea_id: UUID
    dia: Weekday
    bloque_inicio: time
    bloque_fin: time
    orden: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_window(self):
        if self.bloque_fin <= self.bloque_inicio:
            raise ValueError("bloque_fin debe ser mayor que bloque_inicio")
        return self


class ClaudeConflict(BaseModel):
    tarea_id: UUID | None = None
    tipo: str
    severidad: Literal["info", "advertencia", "critico"]
    mensaje: str


class ClaudePlanResponse(BaseModel):
    version_plan: str
    viabilidad: Literal["viable", "viable_con_ajustes", "no_viable"]
    plan: list[ClaudePlanItem]
    justificacion: str
    riesgos: list[str] = []
    conflictos: list[ClaudeConflict] = []
    recomendaciones: list[str] = []


def _strip_fences(payload: str) -> str:
    cleaned = payload.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_claude_response(payload: str, allowed_task_ids: Iterable[UUID]) -> ClaudePlanResponse:
    normalized = _strip_fences(payload)
    data = json.loads(normalized)
    response = ClaudePlanResponse.model_validate(data)

    allowed = {str(task_id) for task_id in allowed_task_ids}
    for item in response.plan:
        if str(item.tarea_id) not in allowed:
            raise ValueError(f"tarea_id inválido: {item.tarea_id}")

    return response


def validate_claude_response(payload: str, allowed_task_ids: Iterable[UUID]) -> ClaudePlanResponse:
    try:
        return parse_claude_response(payload, allowed_task_ids)
    except (json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ValueError(str(error)) from error