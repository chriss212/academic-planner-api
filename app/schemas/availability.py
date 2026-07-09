from pydantic import BaseModel, Field, model_validator
from datetime import date, time
from uuid import UUID
from typing import Optional

class AvailabilityCreate(BaseModel):
    block_date: date
    start_time: time
    end_time:   time
    label:      Optional[str] = None

    @model_validator(mode="after")
    def check_time_order(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time debe ser mayor que start_time")
        return self

class AvailabilityOut(BaseModel):
    id:         UUID
    user_id:    UUID
    block_date: date
    start_time: time
    end_time:   time
    label:      Optional[str]

    model_config = {"from_attributes": True}