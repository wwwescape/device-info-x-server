from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_release import AppRelease


async def get_latest_build(db: AsyncSession) -> str | None:
    result = await db.execute(select(AppRelease).limit(1))
    release = result.scalar_one_or_none()
    return release.build_timestamp if release is not None else None


async def set_latest_build(db: AsyncSession, build_timestamp: str) -> AppRelease:
    """Updates the single existing row in place if one exists, otherwise creates it — the CLI's
    `set-latest-build` command is the only caller, run by hand right after cutting a build (see
    `AppRelease`'s own doc comment for why this is a single row rather than a history table)."""
    result = await db.execute(select(AppRelease).limit(1))
    release = result.scalar_one_or_none()
    if release is not None:
        release.build_timestamp = build_timestamp
    else:
        release = AppRelease(build_timestamp=build_timestamp)
        db.add(release)
    await db.commit()
    await db.refresh(release)
    return release
