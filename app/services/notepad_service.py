import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.notepad import NotepadEntry, NotepadEntryType
from app.models.user import User
from app.repositories import notepad_repo
from app.schemas.notepad import NotepadEntryCreate, NotepadEntryOut, NotepadEntryUpdate
from app.services import notification_service


def _to_out(entry: NotepadEntry) -> NotepadEntryOut:
    return NotepadEntryOut(
        id=entry.id,
        type=entry.type,
        owner_id=entry.owner_id,
        title=entry.title,
        body=entry.body,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        updated_by=entry.updated_by,
    )


async def _get_authorized(db: AsyncSession, current_user: User, entry_id: uuid.UUID) -> NotepadEntry:
    """PRIVATE entries 404 (not 403) for anyone but their owner — a private note must stay
    genuinely invisible to the partner, not merely partner-can't-edit (unlike Safe Locker's
    shared-but-owner-edits-only model, which 403s instead since existence there is never meant to
    be hidden). SHARED entries have no further check beyond existing — the router's own
    `require_paired` already guarantees the caller is one of exactly the 2 users who could ever
    reach this endpoint."""
    entry = await notepad_repo.get_by_id(db, entry_id)
    if entry is None:
        raise NotFoundError("notepad entry not found")
    if entry.type == NotepadEntryType.PRIVATE and entry.owner_id != current_user.id:
        raise NotFoundError("notepad entry not found")
    return entry


async def _push(
    current_user: User, entry_type: NotepadEntryType, entry_id: uuid.UUID, event_suffix: str, ws_data: dict
) -> None:
    """Takes primitives, not the ORM row, so it's safe to call after a delete+commit (the row is
    gone by then; touching an expired/deleted ORM attribute would re-hit the DB and fail — see
    `delete_entry`, which mirrors `locker_service.delete_album`'s own "pass the id, not the row"
    precedent for exactly this reason).

    PRIVATE pushes only to the owner's own other devices (mirrors `message_service.set_starred`'s
    "starring is private" scoping) — the partner is never notified, since they can't see this
    entry at all. SHARED pushes only to the partner (mirrors `locker_service`/`calendar_service` —
    neither pushes back to the actor's own other devices either; a SHARED entry's cross-device
    consistency for the actor themselves is eventually-consistent via the next `refresh()`, same
    limitation those two already have)."""
    if entry_type == NotepadEntryType.PRIVATE:
        target_id = current_user.id
    else:
        if current_user.partner_id is None:
            return
        target_id = current_user.partner_id
    await notification_service.notify_user(
        target_id,
        f"notepad.entry.{event_suffix}",
        ws_data,
        fcm_data={"type": f"notepad_entry_{event_suffix}", "entry_id": str(entry_id)},
    )


async def list_private(db: AsyncSession, current_user: User) -> list[NotepadEntryOut]:
    return [_to_out(e) for e in await notepad_repo.list_private_for_owner(db, current_user.id)]


async def list_shared(db: AsyncSession) -> list[NotepadEntryOut]:
    return [_to_out(e) for e in await notepad_repo.list_shared(db)]


async def create_entry(db: AsyncSession, current_user: User, payload: NotepadEntryCreate) -> NotepadEntryOut:
    entry = await notepad_repo.create(
        db,
        type=payload.type,
        owner_id=current_user.id if payload.type == NotepadEntryType.PRIVATE else None,
        title=payload.title,
        body=payload.body,
        updated_by=current_user.id,
    )
    await db.commit()
    await db.refresh(entry)

    out = _to_out(entry)
    await _push(current_user, entry.type, entry.id, "created", {"entry": out.model_dump(mode="json")})
    return out


async def update_entry(
    db: AsyncSession, current_user: User, entry_id: uuid.UUID, payload: NotepadEntryUpdate
) -> NotepadEntryOut:
    entry = await _get_authorized(db, current_user, entry_id)
    # The optimistic-concurrency check — see NotepadEntry's own doc comment for why this exists
    # and why it's a first for this codebase. SHARED only: a PRIVATE entry has exactly one
    # possible writer (its own owner, across however many of their own devices), so there's
    # nothing meaningful to detect a conflict *against* — always just save the current version,
    # last-write-wins, same as every other single-owner record in this app. Compares the full
    # instant, not a tolerance window, for SHARED: any intervening write (the partner, or this
    # user's other device) must be caught, not just a "big enough" one.
    if entry.type == NotepadEntryType.SHARED and entry.updated_at != payload.expected_updated_at:
        raise ConflictError("this note was changed since you last loaded it")

    entry.title = payload.title
    entry.body = payload.body
    entry.updated_by = current_user.id
    await db.commit()
    await db.refresh(entry)

    out = _to_out(entry)
    await _push(current_user, entry.type, entry.id, "updated", {"entry": out.model_dump(mode="json")})
    return out


async def delete_entry(db: AsyncSession, current_user: User, entry_id: uuid.UUID) -> None:
    entry = await _get_authorized(db, current_user, entry_id)
    entry_type, entry_id_copy = entry.type, entry.id

    await notepad_repo.delete(db, entry)
    await db.commit()

    await _push(current_user, entry_type, entry_id_copy, "deleted", {"entry_id": str(entry_id_copy)})


async def duplicate_entry(db: AsyncSession, current_user: User, entry_id: uuid.UUID) -> NotepadEntryOut:
    """Stays within its own type/owner — duplicating a shared note produces another shared note,
    not a copy into the caller's private list."""
    source = await _get_authorized(db, current_user, entry_id)
    return await create_entry(
        db, current_user, NotepadEntryCreate(type=source.type, title=source.title, body=source.body)
    )
