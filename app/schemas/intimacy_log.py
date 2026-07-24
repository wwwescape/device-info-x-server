from pydantic import BaseModel, Field, field_validator

from app.models.intimacy_log import LOCATIONS, MOODS, POSITIONS


class IntimacyLogCreate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    duration_minutes: int | None = Field(default=None, ge=1)
    # Either the literal sentinel "both" or one of the pair's own user-id strings — validated
    # against the actual pairing in calendar_service, since that depends on runtime state this
    # schema has no access to.
    initiated_by: str | None = None
    protection_used: bool | None = None
    positions: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    moods: list[str] = Field(default_factory=list)
    rounds: int | None = Field(default=None, ge=1, le=10)
    # Either "both", "none", or one of the pair's own user-id strings — validated against the
    # actual pairing in calendar_service, same as initiated_by above.
    orgasmed_by: str | None = None

    @field_validator("positions")
    @classmethod
    def _check_positions(cls, value: list[str]) -> list[str]:
        invalid = set(value) - set(POSITIONS)
        if invalid:
            raise ValueError(f"unknown position(s): {sorted(invalid)}")
        return value

    @field_validator("locations")
    @classmethod
    def _check_locations(cls, value: list[str]) -> list[str]:
        invalid = set(value) - set(LOCATIONS)
        if invalid:
            raise ValueError(f"unknown location(s): {sorted(invalid)}")
        return value

    @field_validator("moods")
    @classmethod
    def _check_moods(cls, value: list[str]) -> list[str]:
        invalid = set(value) - set(MOODS)
        if invalid:
            raise ValueError(f"unknown mood(s): {sorted(invalid)}")
        return value


class IntimacyLogUpdate(IntimacyLogCreate):
    """Same shape as create — the log is always replaced wholesale (see
    `calendar_repo.set_intimacy_log`), never partially patched field-by-field."""


class IntimacyLogOut(BaseModel):
    rating: int | None
    duration_minutes: int | None
    initiated_by: str | None
    protection_used: bool | None
    positions: list[str]
    locations: list[str]
    moods: list[str]
    rounds: int | None
    orgasmed_by: str | None
