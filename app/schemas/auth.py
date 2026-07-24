from datetime import date

from pydantic import BaseModel, Field

from app.models.user import Gender


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    gender: Gender = Gender.UNSPECIFIED
    birthday_date: date
    setup_token: str


class LoginRequest(BaseModel):
    username: str
    password: str
    device_label: str | None = Field(default=None, max_length=128)
    # IANA timezone id, auto-detected client-side — silently refreshes User.timezone on every
    # login so the birthday sweep's local-midnight calculation self-corrects if the user travels.
    timezone: str | None = Field(default=None, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class VerifyPasswordRequest(BaseModel):
    """`POST /auth/verify-password` — re-proves identity for an already-authenticated session
    (e.g. the app's "Forgot code?" local-PIN-reset flow) without minting new tokens the way a
    fresh `/auth/login` call would."""

    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
