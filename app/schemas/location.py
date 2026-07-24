import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LocationUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float | None = None


class PartnerLocationStatus(BaseModel):
    user_id: uuid.UUID
    sharing: bool
    lat: float | None = None
    lng: float | None = None
    accuracy_m: float | None = None
    updated_at: datetime | None = None


class LocationStatusResponse(BaseModel):
    """Pulled once by the map screen on open to seed initial state — everything after that rides
    the live WS relay (`location.update`/`location.enabled`/`location.disabled`), same "REST for
    state, WS+FCM for deltas" split `location_service` uses throughout."""

    self_status: PartnerLocationStatus
    partner_status: PartnerLocationStatus | None = None
