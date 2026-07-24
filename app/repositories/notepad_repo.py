import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notepad import NotepadEntry, NotepadEntryType


async def get_by_id(db: AsyncSession, entry_id: uuid.UUID) -> NotepadEntry | None:
    return await db.get(NotepadEntry, entry_id)


async def list_private_for_owner(db: AsyncSession, owner_id: uuid.UUID) -> list[NotepadEntry]:
    result = await db.execute(
        select(NotepadEntry)
        .where(NotepadEntry.type == NotepadEntryType.PRIVATE, NotepadEntry.owner_id == owner_id)
        .order_by(NotepadEntry.updated_at.desc())
    )
    return list(result.scalars().all())


async def list_shared(db: AsyncSession) -> list[NotepadEntry]:
    result = await db.execute(
        select(NotepadEntry)
        .where(NotepadEntry.type == NotepadEntryType.SHARED)
        .order_by(NotepadEntry.updated_at.desc())
    )
    return list(result.scalars().all())


async def create(db: AsyncSession, **fields) -> NotepadEntry:
    entry = NotepadEntry(**fields)
    db.add(entry)
    await db.flush()
    return entry


async def delete(db: AsyncSession, entry: NotepadEntry) -> None:
    await db.delete(entry)
    await db.flush()
