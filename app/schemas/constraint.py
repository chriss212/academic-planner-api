from pydantic import BaseModel, ConfigDict, Field, model_validator
from uuid import UUID
from datetime import date as date_type, time as time_type
from typing import Optional, Any
from enum import Enum


class ConstraintType(str, Enum):
    blocked_time      = "blocked_time"
    max_session_hours = "max_session_hours"
    fixed_task        = "fixed_task"
    academic_priority = "academic_priority"


WEEKDAYS = {"lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"}


def _parse_time(value: Any, field: str) -> time_type:
    try:
        return time_type.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{field} debe tener formato HH:MM") from error


def validate_constraint_metadata(
    type_: ConstraintType,
    metadata: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Valida y normaliza metadata según el tipo de restricción.

    Lanza ValueError con mensaje claro si la metadata no cumple el contrato
    mínimo que el motor de reglas necesita para poder aplicar la restricción.
    """
    metadata = dict(metadata or {})

    if type_ == ConstraintType.max_session_hours:
        minutes = metadata.get("max_session_minutes")
        hours = metadata.get("max_session_hours")
        if minutes is None and hours is None:
            raise ValueError(
                "max_session_hours requiere metadata.max_session_minutes o metadata.max_session_hours"
            )
        if minutes is not None:
            if not isinstance(minutes, (int, float)) or minutes <= 0:
                raise ValueError("max_session_minutes debe ser un número positivo")
            metadata["max_session_minutes"] = int(minutes)
        else:
            if not isinstance(hours, (int, float)) or hours <= 0:
                raise ValueError("max_session_hours debe ser un número positivo")
            metadata["max_session_minutes"] = int(float(hours) * 60)
        return metadata

    if type_ == ConstraintType.fixed_task:
        task_id = metadata.get("task_id")
        if not task_id:
            raise ValueError("fixed_task requiere metadata.task_id")
        try:
            UUID(str(task_id))
        except ValueError as error:
            raise ValueError("metadata.task_id debe ser un UUID válido") from error

        has_window = any(metadata.get(key) for key in ("date", "start_time", "end_time"))
        if has_window:
            if not metadata.get("date"):
                raise ValueError("fixed_task con horario requiere metadata.date (YYYY-MM-DD)")
            try:
                date_type.fromisoformat(str(metadata["date"]))
            except ValueError as error:
                raise ValueError("metadata.date debe tener formato YYYY-MM-DD") from error
            start = _parse_time(metadata.get("start_time"), "metadata.start_time")
            end = _parse_time(metadata.get("end_time"), "metadata.end_time")
            if end <= start:
                raise ValueError("metadata.end_time debe ser mayor que metadata.start_time")
        return metadata

    if type_ == ConstraintType.blocked_time:
        day = metadata.get("date")
        weekday = metadata.get("weekday")
        if not day and not weekday:
            raise ValueError("blocked_time requiere metadata.date (YYYY-MM-DD) o metadata.weekday")
        if day:
            try:
                date_type.fromisoformat(str(day))
            except ValueError as error:
                raise ValueError("metadata.date debe tener formato YYYY-MM-DD") from error
        if weekday and str(weekday) not in WEEKDAYS:
            raise ValueError(f"metadata.weekday debe ser uno de: {', '.join(sorted(WEEKDAYS))}")
        start = _parse_time(metadata.get("start_time"), "metadata.start_time")
        end = _parse_time(metadata.get("end_time"), "metadata.end_time")
        if end <= start:
            raise ValueError("metadata.end_time debe ser mayor que metadata.start_time")
        return metadata

    return metadata or None


class ConstraintCreate(BaseModel):
    type:        ConstraintType
    description: str
    metadata:    Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def check_metadata(self):
        self.metadata = validate_constraint_metadata(self.type, self.metadata)
        return self


class ConstraintUpdate(BaseModel):
    type:        Optional[ConstraintType] = None
    description: Optional[str] = None
    metadata:    Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def check_metadata(self):
        if self.type is not None and self.metadata is not None:
            self.metadata = validate_constraint_metadata(self.type, self.metadata)
        return self


class ConstraintOut(BaseModel):
    id:          UUID
    user_id:     UUID
    type:        ConstraintType
    description: str
    metadata:    Optional[dict[str, Any]] = Field(default=None, alias="meta_data")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
