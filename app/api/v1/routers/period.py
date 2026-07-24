import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.period import PeriodCycleCreate, PeriodCycleOut, PeriodCycleUpdate
from app.services import period_service

router = APIRouter(prefix="/period", tags=["period"])


@router.get("/cycles", response_model=list[PeriodCycleOut])
async def list_cycles(
    user_id: uuid.UUID | None = Query(default=None, description="Defaults to yourself; may also be your partner"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PeriodCycleOut]:
    return await period_service.list_cycles(db, current_user, user_id)


@router.post("/cycles", response_model=PeriodCycleOut, status_code=status.HTTP_201_CREATED)
async def create_cycle(
    payload: PeriodCycleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PeriodCycleOut:
    return await period_service.create_cycle(db, current_user, payload)


@router.patch("/cycles/{cycle_id}", response_model=PeriodCycleOut)
async def update_cycle(
    cycle_id: uuid.UUID,
    payload: PeriodCycleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PeriodCycleOut:
    return await period_service.update_cycle(db, current_user, cycle_id, payload)


@router.delete("/cycles/{cycle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cycle(
    cycle_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await period_service.delete_cycle(db, current_user, cycle_id)


@router.delete("/cycles", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_cycles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await period_service.delete_all_cycles(db)
