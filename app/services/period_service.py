import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.period import PeriodCycle
from app.models.user import User
from app.repositories import period_repo
from app.schemas.period import PeriodCycleCreate, PeriodCycleOut, PeriodCycleUpdate

# Mirrors CycleRepository.kt's MAX_CYCLES_FOR_AVERAGE/DEFAULT_CYCLE_LENGTH_DAYS on the Android
# side, so the server's forecast (used only to time the two period-notification pushes in
# app/tasks/scheduler.py) lines up with what the client itself predicts and shows the user.
_MAX_CYCLES_FOR_AVERAGE = 6
_DEFAULT_CYCLE_LENGTH_DAYS = 28


def predict_next_cycle_start(cycles_desc: list[PeriodCycle]) -> date | None:
    """Server-side port of CycleRepository.computePrediction's next-start calculation (the
    symptom/duration/fertile-window fields it also computes have no server-side use and are
    left out). [cycles_desc] must be ordered most-recent-first, matching
    `period_repo.list_cycles`'s own ordering.

    Diverges from the client in one case: a single logged cycle there predicts off the user's
    on-device cycleLengthSeedDays estimate (an onboarding value that's never synced to the
    server — see CycleRepository's own doc comment), so here it falls back to the textbook
    28-day average instead until a second cycle exists to average real gaps from."""
    if not cycles_desc:
        return None
    last_start = cycles_desc[0].cycle_start_date
    if len(cycles_desc) == 1:
        cycle_length_days = _DEFAULT_CYCLE_LENGTH_DAYS
    else:
        starts = [c.cycle_start_date for c in cycles_desc[: _MAX_CYCLES_FOR_AVERAGE + 1]]
        gaps = [(newer - older).days for newer, older in zip(starts, starts[1:], strict=False)]
        cycle_length_days = max(1, round(sum(gaps) / len(gaps)))
    return last_start + timedelta(days=cycle_length_days)


def _cycle_out(cycle: PeriodCycle) -> PeriodCycleOut:
    return PeriodCycleOut(
        id=cycle.id,
        user_id=cycle.user_id,
        cycle_start_date=cycle.cycle_start_date,
        cycle_length_days=cycle.cycle_length_days,
        period_end_date=cycle.period_end_date,
        symptoms=cycle.symptoms,
        flow_intensity=cycle.flow_intensity,
        notes=cycle.notes,
        created_at=cycle.created_at,
        updated_at=cycle.updated_at,
    )


async def _get_viewable_cycle(db: AsyncSession, user: User, cycle_id: uuid.UUID) -> PeriodCycle:
    cycle = await period_repo.get_cycle(db, cycle_id)
    if cycle is None:
        raise NotFoundError("cycle not found")
    if cycle.user_id != user.id and cycle.user_id != user.partner_id:
        raise ForbiddenError("not authorized to access this cycle")
    return cycle


def _resolve_target_user_id(user: User, target_user_id: uuid.UUID | None) -> uuid.UUID:
    if target_user_id is None or target_user_id == user.id:
        return user.id
    if target_user_id == user.partner_id:
        return target_user_id
    raise ValidationError("user_id must be yourself or your paired partner")


async def list_cycles(db: AsyncSession, user: User, target_user_id: uuid.UUID | None = None) -> list[PeriodCycleOut]:
    resolved = _resolve_target_user_id(user, target_user_id)
    return [_cycle_out(c) for c in await period_repo.list_cycles(db, resolved)]


async def create_cycle(db: AsyncSession, user: User, payload: PeriodCycleCreate) -> PeriodCycleOut:
    cycle = await period_repo.create_cycle(
        db,
        user_id=user.id,
        cycle_start_date=payload.cycle_start_date,
        cycle_length_days=payload.cycle_length_days,
        period_end_date=payload.period_end_date,
        symptoms=payload.symptoms,
        flow_intensity=payload.flow_intensity,
        notes=payload.notes,
    )
    await db.commit()
    await db.refresh(cycle)
    return _cycle_out(cycle)


async def update_cycle(
    db: AsyncSession, user: User, cycle_id: uuid.UUID, payload: PeriodCycleUpdate
) -> PeriodCycleOut:
    cycle = await _get_viewable_cycle(db, user, cycle_id)
    if cycle.user_id != user.id:
        raise ForbiddenError("only the owner can edit this cycle")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cycle, field, value)
    await db.commit()
    await db.refresh(cycle)
    return _cycle_out(cycle)


async def delete_cycle(db: AsyncSession, user: User, cycle_id: uuid.UUID) -> None:
    cycle = await _get_viewable_cycle(db, user, cycle_id)
    if cycle.user_id != user.id:
        raise ForbiddenError("only the owner can delete this cycle")
    await period_repo.delete_cycle(db, cycle)
    await db.commit()


async def delete_all_cycles(db: AsyncSession) -> None:
    """The "Delete data" action for Period Tracker in the client's Settings screen — wipes both
    partners' logged cycles (see `period_repo.delete_all_cycles`'s doc comment for why that's
    correct given the 2-account cap). No notification — this module never imports
    `notification_service` (Period Tracker has no realtime WS channel at all, matching every
    other mutation here), and this bulk action is no exception; the partner only sees the result
    next time they open or refresh Period Tracker."""
    await period_repo.delete_all_cycles(db)
    await db.commit()
