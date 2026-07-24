import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.period import PeriodDayLog
from app.models.user import User
from app.repositories import period_repo
from app.schemas.period import PeriodDayLogCreate, PeriodDayLogOut, PeriodDayLogUpdate

# Mirrors CycleRepository.kt's MAX_CYCLES_FOR_AVERAGE/DEFAULT_CYCLE_LENGTH_DAYS on the Android
# side, so the server's forecast (used only to time the two period-notification pushes in
# app/tasks/scheduler.py) lines up with what the client itself predicts and shows the user.
_MAX_CYCLES_FOR_AVERAGE = 6
_DEFAULT_CYCLE_LENGTH_DAYS = 28

# A "period day" is any day log with a real flow_intensity set (see PeriodDayLog's own doc
# comment) — a spotting-only or symptom/mood/notes-only day log doesn't start/extend a cycle.
# Two period days up to this many days apart still belong to the same cycle (a single
# skipped/unlogged day mid-period shouldn't fragment it into two), mirroring
# CycleRepository.kt's own CYCLE_GROUP_MAX_GAP_DAYS.
_CYCLE_GROUP_MAX_GAP_DAYS = 1


def _group_into_cycles(day_logs: list[PeriodDayLog]) -> list[date]:
    """Derives cycle start dates from contiguous runs of period days — cycles are never stored,
    only computed here at read time. Returns start dates descending (most recent first), matching
    the ordering `predict_next_cycle_start` (and the old, now-removed `period_repo.list_cycles`)
    always expected."""
    period_days = sorted({log.log_date for log in day_logs if log.flow_intensity is not None})
    if not period_days:
        return []
    starts: list[date] = [period_days[0]]
    for previous, current in zip(period_days, period_days[1:], strict=False):
        if (current - previous).days > _CYCLE_GROUP_MAX_GAP_DAYS + 1:
            starts.append(current)
    starts.reverse()
    return starts


def predict_next_cycle_start(day_logs_desc: list[PeriodDayLog]) -> date | None:
    """Server-side port of CycleRepository.computePrediction's next-start calculation (the
    symptom/duration/fertile-window fields it also computes have no server-side use and are
    left out). [day_logs_desc] must be ordered most-recent-first, matching
    `period_repo.list_day_logs`'s own ordering.

    Diverges from the client in one case: a single derived cycle there predicts off the user's
    on-device cycleLengthSeedDays estimate (an onboarding value that's never synced to the
    server — see CycleRepository's own doc comment), so here it falls back to the textbook
    28-day average instead until a second cycle exists to average real gaps from."""
    cycle_starts_desc = _group_into_cycles(day_logs_desc)
    if not cycle_starts_desc:
        return None
    last_start = cycle_starts_desc[0]
    if len(cycle_starts_desc) == 1:
        cycle_length_days = _DEFAULT_CYCLE_LENGTH_DAYS
    else:
        starts = cycle_starts_desc[: _MAX_CYCLES_FOR_AVERAGE + 1]
        gaps = [(newer - older).days for newer, older in zip(starts, starts[1:], strict=False)]
        cycle_length_days = max(1, round(sum(gaps) / len(gaps)))
    return last_start + timedelta(days=cycle_length_days)


def _day_log_out(day_log: PeriodDayLog) -> PeriodDayLogOut:
    return PeriodDayLogOut(
        id=day_log.id,
        user_id=day_log.user_id,
        log_date=day_log.log_date,
        symptoms=day_log.symptoms,
        flow_intensity=day_log.flow_intensity,
        notes=day_log.notes,
        created_at=day_log.created_at,
        updated_at=day_log.updated_at,
    )


async def _get_viewable_day_log(db: AsyncSession, user: User, day_log_id: uuid.UUID) -> PeriodDayLog:
    day_log = await period_repo.get_day_log(db, day_log_id)
    if day_log is None:
        raise NotFoundError("day log not found")
    if day_log.user_id != user.id and day_log.user_id != user.partner_id:
        raise ForbiddenError("not authorized to access this day log")
    return day_log


def _resolve_target_user_id(user: User, target_user_id: uuid.UUID | None) -> uuid.UUID:
    if target_user_id is None or target_user_id == user.id:
        return user.id
    if target_user_id == user.partner_id:
        return target_user_id
    raise ValidationError("user_id must be yourself or your paired partner")


async def list_day_logs(
    db: AsyncSession, user: User, target_user_id: uuid.UUID | None = None
) -> list[PeriodDayLogOut]:
    resolved = _resolve_target_user_id(user, target_user_id)
    return [_day_log_out(d) for d in await period_repo.list_day_logs(db, resolved)]


async def create_day_log(db: AsyncSession, user: User, payload: PeriodDayLogCreate) -> PeriodDayLogOut:
    existing = await period_repo.get_day_log_by_date(db, user.id, payload.log_date)
    if existing is not None:
        raise ValidationError("a day log already exists for this date — update it instead")
    day_log = await period_repo.create_day_log(
        db,
        user_id=user.id,
        log_date=payload.log_date,
        symptoms=payload.symptoms,
        flow_intensity=payload.flow_intensity,
        notes=payload.notes,
    )
    await db.commit()
    await db.refresh(day_log)
    return _day_log_out(day_log)


async def update_day_log(
    db: AsyncSession, user: User, day_log_id: uuid.UUID, payload: PeriodDayLogUpdate
) -> PeriodDayLogOut:
    day_log = await _get_viewable_day_log(db, user, day_log_id)
    if day_log.user_id != user.id:
        raise ForbiddenError("only the owner can edit this day log")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(day_log, field, value)
    await db.commit()
    await db.refresh(day_log)
    return _day_log_out(day_log)


async def delete_day_log(db: AsyncSession, user: User, day_log_id: uuid.UUID) -> None:
    day_log = await _get_viewable_day_log(db, user, day_log_id)
    if day_log.user_id != user.id:
        raise ForbiddenError("only the owner can delete this day log")
    await period_repo.delete_day_log(db, day_log)
    await db.commit()


async def delete_all_day_logs(db: AsyncSession) -> None:
    """The "Delete data" action for Period Tracker in the client's Settings screen — wipes both
    partners' logged days (see `period_repo.delete_all_day_logs`'s doc comment for why that's
    correct given the 2-account cap). No notification — this module never imports
    `notification_service` (Period Tracker has no realtime WS channel at all, matching every
    other mutation here), and this bulk action is no exception; the partner only sees the result
    next time they open or refresh Period Tracker."""
    await period_repo.delete_all_day_logs(db)
    await db.commit()
