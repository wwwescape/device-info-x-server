from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.security import generate_turn_credentials
from app.models.user import User
from app.schemas.turn import TurnCredentialsResponse

router = APIRouter(prefix="/turn", tags=["turn"])
settings = get_settings()


@router.get("/credentials", response_model=TurnCredentialsResponse)
async def get_turn_credentials(current_user: User = Depends(get_current_user)) -> TurnCredentialsResponse:
    """Time-limited coturn REST-API-style credentials (HMAC over
    `<expiry>:<user_id>` with the shared static-auth-secret). Infra scaffold
    only — no WebRTC call-signaling is implemented yet, this just lets a
    future client obtain TURN/STUN credentials without a migration later."""
    username, credential, ttl = generate_turn_credentials(str(current_user.id))
    return TurnCredentialsResponse(
        urls=settings.turn_urls_list, username=username, credential=credential, ttl=ttl
    )
