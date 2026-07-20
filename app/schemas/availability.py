from pydantic import BaseModel, Field, model_validator, ConfigDict
from datetime import time
from uuid import UUID
from typing import Optional
from enum import Enum

class Weekday(str, Enum):
    lunes = "lunes"
    martes = "martes"
    miercoles = "miercoles"
    jueves = "jueves"
    viernes = "viernes"
    sabado = "sabado"
    domingo = "domingo"

class AvailabilityCreate(BaseModel):
    day: Weekday
    start_time: time
    end_time:   time
    label:      Optional[str] = None

    @model_validator(mode="after")
    def check_time_order(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time debe ser mayor que start_time")
        return self


class AvailabilityUpdate(BaseModel):
    day: Optional[Weekday] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    label: Optional[str] = None

    @model_validator(mode="after")
    def check_time_order(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time debe ser mayor que start_time")
        return self

class AvailabilityOut(BaseModel):
    id:         UUID
    user_id:    UUID
    day:        Weekday
    start_time: time
    end_time:   time
    label:      Optional[str]

    model_config = ConfigDict(from_attributes=True)