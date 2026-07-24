import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insight import Insight


async def create(db: AsyncSession, *, text: str, target_user_id: uuid.UUID | None) -> Insight:
    insight = Insight(text=text, target_user_id=target_user_id)
    db.add(insight)
    await db.commit()
    await db.refresh(insight)
    return insight


async def get_by_id(db: AsyncSession, insight_id: uuid.UUID) -> Insight | None:
    return await db.get(Insight, insight_id)


async def list_all(db: AsyncSession, *, include_disabled: bool = True) -> list[Insight]:
    stmt = select(Insight).order_by(Insight.created_at)
    if not include_disabled:
        stmt = stmt.where(Insight.enabled.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_visible_to(db: AsyncSession, user_id: uuid.UUID) -> list[Insight]:
    """Enabled insights visible to this account: globally-targeted (`target_user_id` null) plus
    any insight targeted at this user_id specifically — a targeted insight never reaches the
    other account, see `Insight`'s own doc comment."""
    result = await db.execute(
        select(Insight)
        .where(Insight.enabled.is_(True))
        .where((Insight.target_user_id.is_(None)) | (Insight.target_user_id == user_id))
        .order_by(Insight.created_at)
    )
    return list(result.scalars().all())


async def set_enabled(db: AsyncSession, insight: Insight, *, enabled: bool) -> None:
    insight.enabled = enabled
    await db.commit()


async def delete(db: AsyncSession, insight: Insight) -> None:
    await db.delete(insight)
    await db.commit()
