import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locker import LockerAlbum, LockerItem


async def get_album_by_id(db: AsyncSession, album_id: uuid.UUID) -> LockerAlbum | None:
    return await db.get(LockerAlbum, album_id)


async def list_albums_for_users(db: AsyncSession, user_ids: list[uuid.UUID]) -> list[LockerAlbum]:
    result = await db.execute(
        select(LockerAlbum).where(LockerAlbum.owner_id.in_(user_ids)).order_by(LockerAlbum.created_at.desc())
    )
    return list(result.scalars().all())


async def create_album(db: AsyncSession, *, owner_id: uuid.UUID, name: str) -> LockerAlbum:
    album = LockerAlbum(owner_id=owner_id, name=name)
    db.add(album)
    await db.flush()
    return album


async def delete_album(db: AsyncSession, album: LockerAlbum) -> None:
    await db.delete(album)
    await db.flush()


async def get_by_id(db: AsyncSession, item_id: uuid.UUID) -> LockerItem | None:
    item = await db.get(LockerItem, item_id)
    if item is not None and item.deleted_at is not None:
        return None
    return item


async def list_for_users(db: AsyncSession, user_ids: list[uuid.UUID]) -> list[LockerItem]:
    result = await db.execute(
        select(LockerItem)
        .where(LockerItem.owner_id.in_(user_ids), LockerItem.deleted_at.is_(None))
        .order_by(LockerItem.created_at.desc())
    )
    return list(result.scalars().all())


async def create(db: AsyncSession, **fields) -> LockerItem:
    item = LockerItem(**fields)
    db.add(item)
    await db.flush()
    return item


async def soft_delete(db: AsyncSession, item: LockerItem) -> None:
    item.deleted_at = datetime.now(UTC)
    await db.flush()


async def bulk_hard_delete_items_for_owner(db: AsyncSession, owner_id: uuid.UUID) -> list[LockerItem]:
    """The "Delete data" action for Safe Locker in the client's Settings screen — a genuine hard
    delete (unlike single-item `soft_delete` above, which never removes the row or its file),
    deliberately chosen since these are private photos and the whole point of this action is that
    they're actually gone. Includes rows already soft-deleted (no `deleted_at` filter) as a
    freebie cleanup of old tombstones. Returns the pre-delete rows (not just ids) so the caller
    can still read `media_id` off each one for file cleanup after they're gone from the table."""
    result = await db.execute(select(LockerItem).where(LockerItem.owner_id == owner_id))
    items = list(result.scalars().all())
    await db.execute(delete(LockerItem).where(LockerItem.owner_id == owner_id))
    return items


async def bulk_hard_delete_albums_for_owner(db: AsyncSession, owner_id: uuid.UUID) -> None:
    """Matches `delete_album` above's existing hard-delete shape — album delete was never
    soft-delete to begin with, so no divergence here, just the bulk form. A partner's item filed
    into one of these albums keeps existing (`LockerItem.album_id` is `ondelete="SET NULL"`), it
    just becomes uncategorized."""
    await db.execute(delete(LockerAlbum).where(LockerAlbum.owner_id == owner_id))
