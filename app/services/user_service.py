from datetime import date

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_asset import MediaCategory
from app.models.user import Gender, User
from app.repositories import media_asset_repo, user_repo
from app.services import media_service, notification_service
from app.storage import files as storage


async def update_profile(
    db: AsyncSession,
    user: User,
    *,
    display_name: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
    gender: Gender | None = None,
    birthday_date: date | None = None,
) -> User:
    if display_name is not None:
        user.display_name = display_name
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    if gender is not None:
        user.gender = gender
    if birthday_date is not None:
        user.birthday_date = birthday_date
    await db.commit()
    await db.refresh(user)
    return user


async def set_avatar(db: AsyncSession, user: User, upload_file: UploadFile) -> User:
    asset = await media_service.upload(db, user, category=MediaCategory.AVATAR, upload_file=upload_file)
    user.avatar_media_id = asset.id
    await db.commit()
    await db.refresh(user)
    return user


async def delete_account(db: AsyncSession, user: User) -> None:
    """"Destroy all data" in the client's Settings screen — the account itself, not just its
    data. `user_repo.delete`'s own doc comment covers why the DB side of this is a single
    statement (every `users.id` FK cascades except `partner_id`, which goes to `SET NULL`); this
    function's job is everything the cascade *can't* do:

    1. Capture `partner_id` before it's gone, to notify the survivor after.
    2. Sweep every media blob this user owns — cascade deletes the `media_assets` rows, never the
       file on disk, so those paths have to be captured and removed here.
    3. Delete the user (cascades everything else) and commit.
    4. Only then remove the on-disk files — after the DB commit succeeds, so a failure here
       leaves orphaned files (low-cost) rather than a rolled-back-but-partially-cleaned-up state.
    5. Reuse `pairing_service.unpair()`'s exact `pairing.updated` event/payload shape so the
       surviving partner's already-existing WS handler (`ServerPairingRepository`) picks this up
       with no client-side changes needed — from the partner's point of view, this looks exactly
       like the deleted user unpaired from them.
    """
    partner_id = user.partner_id
    assets = await media_asset_repo.list_for_owner(db, user.id)
    storage_paths = [asset.storage_path for asset in assets]

    await user_repo.delete(db, user)
    await db.commit()

    for storage_path in storage_paths:
        await storage.delete_file(storage_path)

    if partner_id is not None:
        await notification_service.notify_user(
            partner_id,
            "pairing.updated",
            {"paired": False, "partner": None},
            fcm_data={"type": "pairing_updated"},
        )
