import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.call_log import CallLogStatus, CallLogType


class CallLogOut(BaseModel):
    id: uuid.UUID
    caller_id: uuid.UUID
    callee_id: uuid.UUID
    call_type: CallLogType
    status: CallLogStatus
    started_at: datetime
    duration_seconds: int | None


class CallLogPage(BaseModel):
    items: list[CallLogOut]
