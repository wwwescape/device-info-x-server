import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.locker import LockerAlbum, LockerItem
from app.models.media_asset import MediaCategory
from app.models.user import User
from app.repositories import locker_repo, media_asset_repo
from app.schemas.locker import (
    LockerAlbumCreate,
    LockerAlbumOut,
    LockerAlbumUpdate,
    LockerItemCreate,
    LockerItemOut,
    LockerItemUpdate,
)
from app.services import media_service, notification_service
from app.storage import files as storage


def _to_out(item: LockerItem) -> LockerItemOut:
    return LockerItemOut(
        id=item.id,
        owner_id=item.owner_id,
        title=item.title,
        description=item.description,
        media_id=item.media_id,
        album_id=item.album_id,
        category=item.category,
        is_encrypted=item.is_encrypted,
        encryption_metadata=item.encryption_metadata,
        is_favorite=item.is_favorite,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _album_to_out(album: LockerAlbum) -> LockerAlbumOut:
    return LockerAlbumOut(id=album.id, owner_id=album.owner_id, name=album.name, created_at=album.created_at)


async def _get_authorized(db: AsyncSession, current_user: User, item_id: uuid.UUID) -> LockerItem:
    item = await locker_repo.get_by_id(db, item_id)
    if item is None:
        raise NotFoundError("locker item not found")
    if item.owner_id != current_user.id and item.owner_id != current_user.partner_id:
        raise ForbiddenError("not authorized to access this locker item")
    return item


async def _get_authorized_album(db: AsyncSession, current_user: User, album_id: uuid.UUID) -> LockerAlbum:
    album = await locker_repo.get_album_by_id(db, album_id)
    if album is None:
        raise NotFoundError("locker album not found")
    if album.owner_id != current_user.id and album.owner_id != current_user.partner_id:
        raise ForbiddenError("not authorized to access this locker album")
    return album


async def _validate_album_id(db: AsyncSession, current_user: User, album_id: uuid.UUID) -> None:
    await _get_authorized_album(db, current_user, album_id)


async def list_albums(db: AsyncSession, current_user: User) -> list[LockerAlbumOut]:
    owner_ids = [current_user.id]
    if current_user.partner_id is not None:
        owner_ids.append(current_user.partner_id)
    return [_album_to_out(a) for a in await locker_repo.list_albums_for_users(db, owner_ids)]


async def create_album(db: AsyncSession, current_user: User, payload: LockerAlbumCreate) -> LockerAlbumOut:
    album = await locker_repo.create_album(db, owner_id=current_user.id, name=payload.name)
    await db.commit()
    await db.refresh(album)

    out = _album_to_out(album)
    if current_user.partner_id is not None:
        await notification_service.notify_user(
            current_user.partner_id,
            "locker.album.created",
            {"album": out.model_dump(mode="json")},
            fcm_data={"type": "locker_album_created", "album_id": str(album.id)},
        )
    return out


async def rename_album(
    db: AsyncSession, current_user: User, album_id: uuid.UUID, payload: LockerAlbumUpdate
) -> LockerAlbumOut:
    album = await _get_authorized_album(db, current_user, album_id)
    if album.owner_id != current_user.id:
        raise ForbiddenError("only the owner can rename this locker album")

    album.name = payload.name
    await db.commit()
    await db.refresh(album)

    out = _album_to_out(album)
    if current_user.partner_id is not None:
        await notification_service.notify_user(
            current_user.partner_id,
            "locker.album.updated",
            {"album": out.model_dump(mode="json")},
            fcm_data={"type": "locker_album_updated", "album_id": str(album.id)},
        )
    return out


async def delete_album(db: AsyncSession, current_user: User, album_id: uuid.UUID) -> None:
    album = await _get_authorized_album(db, current_user, album_id)
    if album.owner_id != current_user.id:
        raise ForbiddenError("only the owner can delete this locker album")

    await locker_repo.delete_album(db, album)
    await db.commit()

    if current_user.partner_id is not None:
        await notification_service.notify_user(
            current_user.partner_id,
            "locker.album.deleted",
            {"album_id": str(album_id)},
            fcm_data={"type": "locker_album_deleted", "album_id": str(album_id)},
        )


async def list_items(db: AsyncSession, current_user: User) -> list[LockerItemOut]:
    owner_ids = [current_user.id]
    if current_user.partner_id is not None:
        owner_ids.append(current_user.partner_id)
    return [_to_out(i) for i in await locker_repo.list_for_users(db, owner_ids)]


async def get_item(db: AsyncSession, current_user: User, item_id: uuid.UUID) -> LockerItemOut:
    return _to_out(await _get_authorized(db, current_user, item_id))


async def create_item(db: AsyncSession, current_user: User, payload: LockerItemCreate) -> LockerItemOut:
    if payload.media_id is not None:
        asset = await media_asset_repo.get_by_id(db, payload.media_id)
        if asset is None or asset.owner_id != current_user.id or asset.category != MediaCategory.LOCKER_FILE:
            raise ValidationError("media_id does not reference a valid locker upload")
    if payload.album_id is not None:
        await _validate_album_id(db, current_user, payload.album_id)

    item = await locker_repo.create(
        db,
        owner_id=current_user.id,
        title=payload.title,
        description=payload.description,
        media_id=payload.media_id,
        album_id=payload.album_id,
        category=payload.category,
        is_encrypted=payload.is_encrypted,
        encryption_metadata=payload.encryption_metadata,
        is_favorite=payload.is_favorite,
    )
    await db.commit()
    await db.refresh(item)

    out = _to_out(item)
    if current_user.partner_id is not None:
        await notification_service.notify_user(
            current_user.partner_id,
            "locker.item.created",
            {"item": out.model_dump(mode="json")},
            fcm_data={"type": "locker_item_created", "item_id": str(item.id)},
        )
    return out


async def update_item(
    db: AsyncSession, current_user: User, item_id: uuid.UUID, payload: LockerItemUpdate
) -> LockerItemOut:
    item = await _get_authorized(db, current_user, item_id)
    if item.owner_id != current_user.id:
        raise ForbiddenError("only the owner can edit this locker item")
    if "album_id" in payload.model_fields_set and payload.album_id is not None:
        await _validate_album_id(db, current_user, payload.album_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)

    out = _to_out(item)
    if current_user.partner_id is not None:
        await notification_service.notify_user(
            current_user.partner_id,
            "locker.item.updated",
            {"item": out.model_dump(mode="json")},
            fcm_data={"type": "locker_item_updated", "item_id": str(item.id)},
        )
    return out


async def delete_item(db: AsyncSession, current_user: User, item_id: uuid.UUID) -> None:
    item = await _get_authorized(db, current_user, item_id)
    if item.owner_id != current_user.id:
        raise ForbiddenError("only the owner can delete this locker item")

    await locker_repo.soft_delete(db, item)
    await db.commit()

    if current_user.partner_id is not None:
        await notification_service.notify_user(
            current_user.partner_id,
            "locker.item.deleted",
            {"item_id": str(item_id)},
            fcm_data={"type": "locker_item_deleted", "item_id": str(item_id)},
        )


async def delete_all_own_data(db: AsyncSession, current_user: User) -> None:
    """The "Delete data" action for Safe Locker in the client's Settings screen — owner-scoped
    (matches every other locker mutation's ownership rule), and unlike single-item delete, a
    genuine hard delete with real file cleanup: these are private photos, so "delete" needs to
    mean actually gone, not just hidden. Also clears every album the caller owns.

    DB writes (item delete, album delete, and the now-orphaned media_assets rows, including each
    deleted video's poster thumbnail — see `media_service.delete_assets_with_thumbnails`) all land
    in one commit; the on-disk blobs are only removed *after* that commit succeeds, so a mid-sweep
    failure leaves orphaned files on disk (an acceptable, low-cost failure mode) rather than a
    half-committed, inconsistent database (not acceptable)."""
    items = await locker_repo.bulk_hard_delete_items_for_owner(db, current_user.id)
    await locker_repo.bulk_hard_delete_albums_for_owner(db, current_user.id)

    media_ids = [item.media_id for item in items if item.media_id is not None]
    storage_paths = await media_service.delete_assets_with_thumbnails(db, media_ids)
    await db.commit()

    for storage_path in storage_paths:
        await storage.delete_file(storage_path)

    if current_user.partner_id is not None:
        await notification_service.notify_user(
            current_user.partner_id,
            "locker.bulk_deleted",
            {},
            fcm_data={"type": "locker_bulk_deleted"},
        )
