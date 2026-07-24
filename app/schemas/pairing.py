from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import PartnerPublic


class PartnerCodeCreateResponse(BaseModel):
    """Only response that ever contains the full plaintext code — it is
    never stored and can't be retrieved again after this."""

    code: str
    code_preview: str
    expires_at: datetime


class PartnerCodeStatusResponse(BaseModel):
    has_active_code: bool
    code_preview: str | None = None
    expires_at: datetime | None = None


class PairRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class PairingStatusResponse(BaseModel):
    paired: bool
    partner: PartnerPublic | None = None
