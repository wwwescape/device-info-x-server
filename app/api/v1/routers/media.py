import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models.media_asset import MediaCategory
from app.models.user import User
from app.schemas.media import MediaAssetOut
from app.services import media_service
from app.storage import files as storage

router = APIRouter(prefix="/media", tags=["media"])
settings = get_settings()


@router.post("", response_model=MediaAssetOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    category: MediaCategory = Form(...),
    file: UploadFile = File(...),
    duration_ms: int | None = Form(default=None),
    thumbnail_media_id: uuid.UUID | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MediaAssetOut:
    return await media_service.upload(
        db,
        current_user,
        category=category,
        upload_file=file,
        duration_ms=duration_ms,
        thumbnail_media_id=thumbnail_media_id,
    )


@router.get("/{media_id}", response_model=MediaAssetOut)
async def get_media_metadata(
    media_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MediaAssetOut:
    """Metadata only, no bytes — lets a receiving device learn a video message's
    `thumbnail_media_id` (and any other asset fields) without going through the
    `/download` route, which only ever returns raw bytes. `MessageOut` deliberately never embeds
    a nested `MediaAssetOut` (see `message_service._to_message_out`), so this is the only way to
    resolve that for media this device didn't itself upload."""
    return await media_service.get_authorized(db, current_user, media_id)


@router.get("/{media_id}/download")
async def download_media(
    media_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await media_service.get_authorized(db, current_user, media_id)
    filename = asset.original_filename or str(asset.id)

    if settings.media_serve_mode == "x-accel":
        # Nginx intercepts X-Accel-Redirect and serves the bytes itself from
        # the read-only media_data mount — the file never passes through
        # this Python process. See nginx/conf.d/app.conf.
        return Response(
            status_code=200,
            media_type=asset.mime_type,
            headers={
                "X-Accel-Redirect": f"/protected_media/{asset.storage_path}",
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )

    return FileResponse(storage.absolute_path(asset.storage_path), media_type=asset.mime_type, filename=filename)
