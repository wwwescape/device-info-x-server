import datetime
import uuid

from pydantic import BaseModel, Field

from app.models.period import FlowIntensity


class PeriodCycleCreate(BaseModel):
    cycle_start_date: datetime.date
    cycle_length_days: int | None = Field(default=None, ge=1, le=90)
    period_end_date: datetime.date | None = None
    symptoms: list[str] = Field(default_factory=list)
    flow_intensity: FlowIntensity | None = None
    notes: str | None = None


class PeriodCycleUpdate(BaseModel):
    cycle_start_date: datetime.date | None = None
    cycle_length_days: int | None = Field(default=None, ge=1, le=90)
    period_end_date: datetime.date | None = None
    symptoms: list[str] | None = None
    flow_intensity: FlowIntensity | None = None
    notes: str | None = None


class PeriodCycleOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    cycle_start_date: datetime.date
    cycle_length_days: int | None
    period_end_date: datetime.date | None
    symptoms: list[str]
    flow_intensity: FlowIntensity | None
    notes: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
