import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.calendar_event import EventType
from app.schemas.intimacy_log import IntimacyLogCreate, IntimacyLogOut, IntimacyLogUpdate
from app.schemas.media import MediaAssetOut


class CalendarEventCreate(BaseModel):
    type: EventType
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    location: str | None = Field(default=None, max_length=255)
    # RFC5545 RRULE, e.g. "FREQ=WEEKLY;BYDAY=MO"
    recurrence_rule: str | None = Field(default=None, max_length=255)
    recurrence_end_at: datetime | None = None
    color: str | None = Field(default=None, max_length=16)
    cancelled: bool = False
    cancellation_reason: str | None = None
    reminder_minutes_before: list[int] = Field(default_factory=list)
    intimacy: IntimacyLogCreate | None = None
    attachment_media_ids: list[uuid.UUID] = Field(default_factory=list)
    cover_media_id: uuid.UUID | None = None


class CalendarEventUpdate(BaseModel):
    type: EventType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    location: str | None = None
    recurrence_rule: str | None = None
    recurrence_end_at: datetime | None = None
    color: str | None = None
    cancelled: bool | None = None
    cancellation_reason: str | None = None
    reminder_minutes_before: list[int] | None = None
    # None = leave the existing log untouched; a value replaces it wholesale — same
    # "None means don't touch, a value replaces" convention as reminder_minutes_before.
    intimacy: IntimacyLogUpdate | None = None
    # Same "None = don't touch, a value replaces the whole list" convention.
    attachment_media_ids: list[uuid.UUID] | None = None
    # Unlike attachment_media_ids, this app's client always resends this field wholesale on every
    # update (the kept existing id, a new upload's id, or null) rather than diffing — see
    # CalendarEventUpdateDto's own doc comment — so exclude_unset's usual "absent = don't touch"
    # reading in practice only ever fires for a genuinely different client integration.
    cover_media_id: uuid.UUID | None = None


class CalendarEventOut(BaseModel):
    id: uuid.UUID
    created_by: uuid.UUID
    type: EventType
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime | None
    all_day: bool
    location: str | None
    recurrence_rule: str | None
    recurrence_end_at: datetime | None
    color: str | None
    cancelled: bool
    cancellation_reason: str | None
    reminder_minutes_before: list[int]
    intimacy: IntimacyLogOut | None
    attachments: list[MediaAssetOut] = Field(default_factory=list)
    cover_media: MediaAssetOut | None = None
    created_at: datetime
    updated_at: datetime
