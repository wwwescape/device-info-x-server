import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import Gender


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    first_name: str
    last_name: str
    avatar_media_id: uuid.UUID | None = None
    partner_id: uuid.UUID | None = None
    gender: Gender
    birthday_date: date
    last_seen_at: datetime | None = None
    created_at: datetime
    must_change_password: bool


class PartnerPublic(BaseModel):
    """What one partner is allowed to see about the other — no email/username
    beyond what's already shared, just presence-relevant profile fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    first_name: str
    last_name: str
    avatar_media_id: uuid.UUID | None = None
    gender: Gender
    birthday_date: date
    last_seen_at: datetime | None = None


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    gender: Gender | None = None
    birthday_date: date | None = None
