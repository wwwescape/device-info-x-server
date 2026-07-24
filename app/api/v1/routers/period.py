import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.period import PeriodDayLogCreate, PeriodDayLogOut, PeriodDayLogUpdate
from app.services import period_service

router = APIRouter(prefix="/period", tags=["period"])


@router.get("/days", response_model=list[PeriodDayLogOut])
async def list_day_logs(
    user_id: uuid.UUID | None = Query(default=None, description="Defaults to yourself; may also be your partner"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PeriodDayLogOut]:
    return await period_service.list_day_logs(db, current_user, user_id)


@router.post("/days", response_model=PeriodDayLogOut, status_code=status.HTTP_201_CREATED)
async def create_day_log(
    payload: PeriodDayLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PeriodDayLogOut:
    return await period_service.create_day_log(db, current_user, payload)


@router.patch("/days/{day_log_id}", response_model=PeriodDayLogOut)
async def update_day_log(
    day_log_id: uuid.UUID,
    payload: PeriodDayLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PeriodDayLogOut:
    return await period_service.update_day_log(db, current_user, day_log_id, payload)


@router.delete("/days/{day_log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_day_log(
    day_log_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await period_service.delete_day_log(db, current_user, day_log_id)


@router.delete("/days", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_day_logs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await period_service.delete_all_day_logs(db)
