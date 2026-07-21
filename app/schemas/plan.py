from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


PlanScope = Literal["diario", "semanal"]
Viabilidad = Literal["viable", "viable_con_ajustes", "no_viable"]
ResponseStatus = Literal["valid", "invalid", "error"]


class PlanItemOut(BaseModel):
    tarea_id: UUID
    dia: date
    bloque_inicio: time
    bloque_fin: time
    orden: int = Field(ge=1)
    task_title: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None


class PlanConflictOut(BaseModel):
    tarea_id: Optional[UUID] = None
    tipo: str
    severidad: Literal["info", "advertencia", "critico"]
    mensaje: str


class PlanGenerationRequest(BaseModel):
    scope: PlanScope = "semanal"
    user_note: Optional[str] = None
    change_block: Optional[dict[str, object]] = None


class PlanGenerationResponse(BaseModel):
    id: UUID
    version: int
    version_plan: str
    scope: PlanScope
    generated_at: datetime
    approval_status: Literal["propuesto", "aprobado", "editado", "rechazado"]
    viabilidad: Viabilidad
    plan: list[PlanItemOut]
    justificacion: str
    riesgos: list[str]
    conflictos: list[PlanConflictOut]
    recomendaciones: list[str]
    prompt_enviado: str
    respuesta_ia: str
    response_status: ResponseStatus
    modelo_usado: str
    validation_code: Optional[str] = None
    estado_revision: Literal["normal", "requiere_revision"] = "normal"

    model_config = ConfigDict(from_attributes=True)


class PlanApprovalUpdate(BaseModel):
    approval_status: Literal["propuesto", "aprobado", "editado", "rechazado"]
    user_note: Optional[str] = None


class PlanManualUpdate(BaseModel):
    plan: list[PlanItemOut]
    user_note: Optional[str] = None