import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_paired
from app.models.user import User
from app.schemas.calendar import CalendarEventCreate, CalendarEventOut, CalendarEventUpdate
from app.services import calendar_service

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def wipe_calendar(
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await calendar_service.wipe_shared_calendar(db, current_user)


@router.get("/events", response_model=list[CalendarEventOut])
async def list_events(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CalendarEventOut]:
    return await calendar_service.list_events(db, start=from_, end=to)


@router.post("/events", response_model=CalendarEventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: CalendarEventCreate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> CalendarEventOut:
    return await calendar_service.create_event(db, current_user, payload)


@router.get("/events/{event_id}", response_model=CalendarEventOut)
async def get_event(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarEventOut:
    return await calendar_service.get_event(db, event_id)


@router.patch("/events/{event_id}", response_model=CalendarEventOut)
async def update_event(
    event_id: uuid.UUID,
    payload: CalendarEventUpdate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> CalendarEventOut:
    return await calendar_service.update_event(db, current_user, event_id, payload)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await calendar_service.delete_event(db, current_user, event_id)
