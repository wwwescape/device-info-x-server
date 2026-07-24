import mimetypes
import uuid
from io import BytesIO

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.media_asset import MediaAsset, MediaCategory
from app.models.user import User
from app.repositories import media_asset_repo
from app.storage import files as storage

settings = get_settings()

_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_VOICE_MIME_TYPES = {
    "audio/aac",
    "audio/mp4",
    "audio/m4a",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/3gpp",
}
_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/3gpp",
    "video/x-matroska",
}
# Duration is opaque bytes to this service (no ffprobe dependency) — the
# client probes it locally and passes it through, same as it already does
# for voice notes.
_DURATION_CATEGORIES = (
    MediaCategory.MESSAGE_VOICE,
    MediaCategory.MESSAGE_VIDEO,
    MediaCategory.CALENDAR_VIDEO,
    MediaCategory.LOCKER_FILE,
)

# A video category's thumbnail must itself be an upload of the paired image category — mirrors
# each video category's own family (message video's poster frame is a message image, calendar
# video's is a calendar image), enforced in upload()'s thumbnail_media_id validation below.
# LOCKER_FILE is self-referential — unlike Messages/Calendar's paired image/video categories,
# Locker has exactly one MediaCategory covering every item kind (photo/video/document); the
# actual kind lives on LockerItem.category instead, one layer up.
_VIDEO_THUMBNAIL_CATEGORY = {
    MediaCategory.MESSAGE_VIDEO: MediaCategory.MESSAGE_IMAGE,
    MediaCategory.CALENDAR_VIDEO: MediaCategory.CALENDAR_IMAGE,
    MediaCategory.LOCKER_FILE: MediaCategory.LOCKER_FILE,
}

# (allowed mime types, or None for "any" — locker files may one day be opaque
# encrypted blobs — and the per-category size cap in MB)
_CATEGORY_RULES: dict[MediaCategory, tuple[set[str] | None, int]] = {
    MediaCategory.MESSAGE_IMAGE: (_IMAGE_MIME_TYPES, settings.max_image_size_mb),
    MediaCategory.AVATAR: (_IMAGE_MIME_TYPES, settings.max_avatar_size_mb),
    MediaCategory.MESSAGE_VOICE: (_VOICE_MIME_TYPES, settings.max_voice_size_mb),
    MediaCategory.MESSAGE_VIDEO: (_VIDEO_MIME_TYPES, settings.max_video_size_mb),
    # None mirrors LOCKER_FILE's own "arbitrary file type" precedent — a document message can be
    # anything the user picks.
    MediaCategory.MESSAGE_DOCUMENT: (None, settings.max_document_size_mb),
    MediaCategory.LOCKER_FILE: (None, settings.max_locker_file_size_mb),
    # link_preview_service already caps the fetch itself at 5MB — this rule only matters if that
    # cap ever changes without this one being revisited too.
    MediaCategory.MESSAGE_LINK_PREVIEW: (_IMAGE_MIME_TYPES, 5),
    # Calendar attachments reuse the exact same mime/size rules as their message-media
    # counterparts — a dedicated category (rather than reusing MESSAGE_*) is purely so an
    # asset's category always tells you which feature it belongs to.
    MediaCategory.CALENDAR_IMAGE: (_IMAGE_MIME_TYPES, settings.max_image_size_mb),
    MediaCategory.CALENDAR_VIDEO: (_VIDEO_MIME_TYPES, settings.max_video_size_mb),
    MediaCategory.CALENDAR_DOCUMENT: (None, settings.max_document_size_mb),
}


def _extension_for(filename: str | None, mime_type: str) -> str:
    if filename and "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()[:10]
    return mimetypes.guess_extension(mime_type) or ""


def _probe_image_dimensions(content: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(BytesIO(content)) as img:
            return img.width, img.height
    except Exception:
        return None, None


async def store_fetched_bytes(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    category: MediaCategory,
    content: bytes,
    mime_type: str,
    original_filename: str | None = None,
    duration_ms: int | None = None,
    thumbnail_media_id: uuid.UUID | None = None,
) -> MediaAsset:
    """The storage/DB tail shared with `upload()` below, factored out for callers that already
    have raw bytes in hand rather than a request-bound `UploadFile` — currently only
    `message_service._fetch_and_attach_link_preview`, storing a fetched OpenGraph image. Skips
    `upload()`'s mime/size validation since that's the caller's responsibility here (the fetch
    itself already caps size and checks Content-Type before this is ever called)."""
    extension = _extension_for(original_filename, mime_type)
    storage_path, checksum, size_bytes = await storage.save_upload(category.value, extension, content)

    width = height = None
    if category in (
        MediaCategory.MESSAGE_IMAGE,
        MediaCategory.AVATAR,
        MediaCategory.MESSAGE_LINK_PREVIEW,
        MediaCategory.CALENDAR_IMAGE,
    ):
        width, height = _probe_image_dimensions(content)

    asset = await media_asset_repo.create(
        db,
        owner_id=owner_id,
        category=category,
        storage_path=storage_path,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum,
        width=width,
        height=height,
        duration_ms=duration_ms if category in _DURATION_CATEGORIES else None,
        thumbnail_media_id=thumbnail_media_id,
    )
    await db.commit()
    await db.refresh(asset)
    return asset


async def upload(
    db: AsyncSession,
    owner: User,
    *,
    category: MediaCategory,
    upload_file: UploadFile,
    duration_ms: int | None = None,
    thumbnail_media_id: uuid.UUID | None = None,
) -> MediaAsset:
    allowed_mimes, max_mb = _CATEGORY_RULES[category]
    mime_type = upload_file.content_type or "application/octet-stream"
    if allowed_mimes is not None and mime_type not in allowed_mimes:
        raise ValidationError(f"unsupported file type for {category.value}: {mime_type}")

    content = await upload_file.read()
    if len(content) == 0:
        raise ValidationError("uploaded file is empty")
    max_bytes = max_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValidationError(f"file exceeds the {max_mb}MB limit for {category.value}")

    if thumbnail_media_id is not None:
        expected_thumbnail_category = _VIDEO_THUMBNAIL_CATEGORY.get(category)
        if expected_thumbnail_category is None:
            raise ValidationError(f"thumbnail_media_id is not valid for {category.value} uploads")
        thumbnail = await media_asset_repo.get_by_id(db, thumbnail_media_id)
        if (
            thumbnail is None
            or thumbnail.owner_id != owner.id
            or thumbnail.category != expected_thumbnail_category
        ):
            raise ValidationError("thumbnail_media_id does not reference a valid image upload")

    return await store_fetched_bytes(
        db,
        owner_id=owner.id,
        category=category,
        content=content,
        mime_type=mime_type,
        original_filename=upload_file.filename,
        duration_ms=duration_ms,
        thumbnail_media_id=thumbnail_media_id,
    )


async def delete_assets_with_thumbnails(db: AsyncSession, media_ids: list[uuid.UUID]) -> list[str]:
    """Hard-deletes every asset in `media_ids` plus each one's video thumbnail, if any.
    `thumbnail_media_id` is just a plain FK column on the video's own row (`ondelete="SET NULL"`
    only handles the reverse direction — deleting the *thumbnail* row nulls out whoever pointed
    at it) — nothing cascades a video's deletion onto its thumbnail, so a caller that deletes only
    the ids it directly knows about (a message's `media_id`, a locker item's `media_id`, a calendar
    attachment's `media_id`) leaves the paired poster-frame row and file orphaned forever. Shared
    by every "Delete data" bulk wipe. Doesn't commit — callers commit once, then remove the
    returned storage_paths from disk, same ordering every wipe already used before this existed."""
    storage_paths: list[str] = []
    seen: set[uuid.UUID] = set()
    for media_id in media_ids:
        if media_id in seen:
            continue
        asset = await media_asset_repo.get_by_id(db, media_id)
        if asset is None:
            continue
        seen.add(media_id)
        if asset.thumbnail_media_id is not None and asset.thumbnail_media_id not in seen:
            thumbnail = await media_asset_repo.get_by_id(db, asset.thumbnail_media_id)
            if thumbnail is not None:
                seen.add(thumbnail.id)
                storage_paths.append(thumbnail.storage_path)
                await media_asset_repo.delete(db, thumbnail)
        storage_paths.append(asset.storage_path)
        await media_asset_repo.delete(db, asset)
    return storage_paths


async def get_authorized(db: AsyncSession, current_user: User, media_id: uuid.UUID) -> MediaAsset:
    asset = await media_asset_repo.get_by_id(db, media_id)
    if asset is None:
        raise NotFoundError("media not found")
    if asset.owner_id != current_user.id and asset.owner_id != current_user.partner_id:
        raise ForbiddenError("not authorized to access this media")
    return asset
