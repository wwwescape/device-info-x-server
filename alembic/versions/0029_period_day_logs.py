"""replace period_cycles (one row per whole period) with period_day_logs (one row per day)

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-14

"""

import uuid
from collections.abc import Sequence
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A cap on how many days a single legacy cycle's [cycle_start_date, period_end_date] range can
# expand into — generous (no real logged period is anywhere near this long), just a guard against
# a corrupt/garbage range turning into an unbounded insert loop.
_MAX_BACKFILL_DAYS = 60


def upgrade() -> None:
    op.create_table(
        "period_day_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("symptoms", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column(
            "flow_intensity",
            # create_type=False — this enum type already exists (created for period_cycles'
            # own flow_intensity column, and dropping that table below doesn't drop the type).
            postgresql.ENUM("light", "medium", "heavy", name="flow_intensity", create_type=False),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_period_day_logs_user_id_users", ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "log_date", name="uq_period_day_logs_user_date"),
    )
    op.create_index("ix_period_day_logs_user_id", "period_day_logs", ["user_id"])
    op.create_index("ix_period_day_logs_log_date", "period_day_logs", ["log_date"])

    day_logs_table = sa.table(
        "period_day_logs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
        sa.column("log_date", sa.Date()),
        sa.column("symptoms", postgresql.ARRAY(sa.String())),
        sa.column(
            "flow_intensity", postgresql.ENUM("light", "medium", "heavy", name="flow_intensity", create_type=False)
        ),
        sa.column("notes", sa.Text()),
    )

    bind = op.get_bind()
    # Backfill: every legacy cycle-level row is expanded into one day_log row per date in
    # [cycle_start_date, period_end_date or cycle_start_date] inclusive, carrying that cycle's
    # flow/symptoms/notes onto every expanded day — the best available signal from range-level
    # data, since per-day granularity never existed before this migration.
    cycles = bind.execute(
        sa.text(
            "SELECT id, user_id, cycle_start_date, period_end_date, symptoms, flow_intensity, notes "
            "FROM period_cycles ORDER BY cycle_start_date"
        )
    ).fetchall()

    seen_user_dates: set[tuple[uuid.UUID, object]] = set()
    rows_to_insert = []
    for cycle in cycles:
        start = cycle.cycle_start_date
        end = cycle.period_end_date or start
        if end < start:
            end = start
        span_days = min((end - start).days, _MAX_BACKFILL_DAYS - 1)
        for offset in range(span_days + 1):
            log_date = start + timedelta(days=offset)
            key = (cycle.user_id, log_date)
            if key in seen_user_dates:
                # Two legacy cycles overlapped on this date (bad pre-existing data) — first one
                # wins, matching an ON CONFLICT DO NOTHING write.
                continue
            seen_user_dates.add(key)
            rows_to_insert.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": cycle.user_id,
                    "log_date": log_date,
                    "symptoms": cycle.symptoms or [],
                    "flow_intensity": cycle.flow_intensity,
                    "notes": cycle.notes,
                }
            )

    if rows_to_insert:
        bind.execute(day_logs_table.insert(), rows_to_insert)

    op.drop_table("period_cycles")


def downgrade() -> None:
    # Recreating period_cycles (and re-collapsing day logs back into ranges) isn't a migration to
    # run automatically — do it by hand if this ever needs undoing, same precedent as 0010's own
    # downgrade.
    raise NotImplementedError("cannot cleanly collapse day logs back into cycles; downgrade manually if needed")
