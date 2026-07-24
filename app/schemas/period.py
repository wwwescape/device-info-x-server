import datetime
import uuid

from pydantic import BaseModel, Field

from app.models.period import FlowIntensity


class PeriodDayLogCreate(BaseModel):
    log_date: datetime.date
    symptoms: list[str] = Field(default_factory=list)
    flow_intensity: FlowIntensity | None = None
    notes: str | None = None


class PeriodDayLogUpdate(BaseModel):
    log_date: datetime.date | None = None
    symptoms: list[str] | None = None
    flow_intensity: FlowIntensity | None = None
    notes: str | None = None


class PeriodDayLogOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    log_date: datetime.date
    symptoms: list[str]
    flow_intensity: FlowIntensity | None
    notes: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
