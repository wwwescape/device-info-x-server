from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.release import ReleaseOut
from app.services import release_service

router = APIRouter(prefix="/releases", tags=["releases"])


@router.get("/latest")
async def latest_release(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReleaseOut:
    """`get_current_user`, not `require_paired` — checking for an update shouldn't require having
    a partner paired yet. `download_url` comes from server config (`APK_DOWNLOAD_URL`), not this
    table — see `AppRelease`'s own doc comment for why the two are split (one changes per build,
    the other essentially never)."""
    latest_build = await release_service.get_latest_build(db)
    return ReleaseOut(latest_build=latest_build, download_url=get_settings().apk_download_url or None)
