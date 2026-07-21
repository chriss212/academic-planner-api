"""Contratos y validación de la respuesta del modelo de IA.

Dos niveles (diseño técnico, sección 3.3.3):
- Wire: el esquema estricto que OpenAI Structured Outputs garantiza (tipos JSON simples).
- Dominio: tipos ricos (UUID, date, time) + reglas estructurales (tarea_id permitido,
  ventana horaria coherente). El nivel 2 (reglas de negocio) vive en services/validation.py.
"""
from __future__ import annotations

import json
import re
from datetime import date, time
from typing import Iterable, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, model_validator



class AIPlanItemWire(BaseModel):
    tarea_id: str
    dia: str = Field(description="Fecha en formato YYYY-MM-DD")
    bloque_inicio: str = Field(description="Hora en formato HH:MM")
    bloque_fin: str = Field(description="Hora en formato HH:MM")
    orden: int


class AIConflictWire(BaseModel):
    tarea_id: Optional[str]
    tipo: str
    severidad: Literal["info", "advertencia", "critico"]
    mensaje: str


class AIPlanResponseWire(BaseModel):
    version_plan: str
    viabilidad: Literal["viable", "viable_con_ajustes", "no_viable"]
    plan: list[AIPlanItemWire]
    justificacion: str
    riesgos: list[str]
    conflictos: list[AIConflictWire]
    recomendaciones: list[str]

class AIPlanItem(BaseModel):
    tarea_id: UUID
    dia: date
    bloque_inicio: time
    bloque_fin: time
    orden: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_window(self):
        if self.bloque_fin <= self.bloque_inicio:
            raise ValueError("bloque_fin debe ser mayor que bloque_inicio")
        return self


class AIConflict(BaseModel):
    tarea_id: UUID | None = None
    tipo: str
    severidad: Literal["info", "advertencia", "critico"]
    mensaje: str


class AIPlanResponse(BaseModel):
    version_plan: str
    viabilidad: Literal["viable", "viable_con_ajustes", "no_viable"]
    plan: list[AIPlanItem]
    justificacion: str
    riesgos: list[str] = []
    conflictos: list[AIConflict] = []
    recomendaciones: list[str] = []


def _strip_fences(payload: str) -> str:
    cleaned = payload.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _check_task_ids(response: AIPlanResponse, allowed_task_ids: Iterable[UUID]) -> AIPlanResponse:
    allowed = {str(task_id) for task_id in allowed_task_ids}
    for item in response.plan:
        if str(item.tarea_id) not in allowed:
            raise ValueError(f"tarea_id inválido: {item.tarea_id}")
    return response


def validate_wire_response(wire: AIPlanResponseWire, allowed_task_ids: Iterable[UUID]) -> AIPlanResponse:
    """Convierte el wire model (garantizado por Structured Outputs) al modelo de dominio."""
    try:
        response = AIPlanResponse.model_validate(wire.model_dump())
    except ValidationError as error:
        raise ValueError(str(error)) from error
    return _check_task_ids(response, allowed_task_ids)


def parse_ai_response(payload: str, allowed_task_ids: Iterable[UUID]) -> AIPlanResponse:
    """Parsea texto crudo (con o sin fences markdown) al modelo de dominio."""
    normalized = _strip_fences(payload)
    data = json.loads(normalized)
    response = AIPlanResponse.model_validate(data)
    return _check_task_ids(response, allowed_task_ids)


def validate_ai_response(payload: str, allowed_task_ids: Iterable[UUID]) -> AIPlanResponse:
    try:
        return parse_ai_response(payload, allowed_task_ids)
    except (json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ValueError(str(error)) from error
