import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_asset import MediaAsset


async def get_by_id(db: AsyncSession, media_id: uuid.UUID) -> MediaAsset | None:
    return await db.get(MediaAsset, media_id)


async def get_by_ids(db: AsyncSession, ids: list[uuid.UUID]) -> list[MediaAsset]:
    """Batch resolve — used by `calendar_repo.attachments_for_events` to avoid N+1 querying
    when a page of events collectively references many media assets."""
    if not ids:
        return []
    result = await db.execute(select(MediaAsset).where(MediaAsset.id.in_(ids)))
    return list(result.scalars().all())


async def list_for_owner(db: AsyncSession, owner_id: uuid.UUID) -> list[MediaAsset]:
    """Used by full account deletion to capture every blob this user owns before the `users.id`
    cascade removes the `media_assets` rows themselves — cascade only deletes DB rows, never the
    on-disk file, so the caller needs this list to sweep those separately."""
    result = await db.execute(select(MediaAsset).where(MediaAsset.owner_id == owner_id))
    return list(result.scalars().all())


async def create(db: AsyncSession, **fields) -> MediaAsset:
    asset = MediaAsset(**fields)
    db.add(asset)
    await db.flush()
    return asset


async def delete(db: AsyncSession, asset: MediaAsset) -> None:
    await db.delete(asset)
    await db.flush()
