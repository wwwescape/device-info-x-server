import datetime
import uuid

from pydantic import BaseModel, Field


class ScheduledMessageCreate(BaseModel):
    # Non-empty, unlike Notepad's blank-allowed body — a scheduled message only ever comes from a
    # composer that already has real typed text (Schedule Send is offered alongside Send, not
    # instead of a blank-composer state), matching message_service.send_message's own "text
    # messages require a non-empty body" check for a live send.
    body: str = Field(min_length=1, max_length=8000)
    scheduled_at: datetime.datetime


class ScheduledMessageOut(BaseModel):
    id: uuid.UUID
    body: str
    scheduled_at: datetime.datetime
    created_at: datetime.datetime
