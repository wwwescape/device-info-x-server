"""special_event_type: add WEDDING_ANNIVERSARY, UNPLANNED_DATE; backfill non-recurring types

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-03

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic wraps
    # migrations in by default, so it needs its own autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE special_event_type ADD VALUE IF NOT EXISTS 'wedding_anniversary'")
        op.execute("ALTER TYPE special_event_type ADD VALUE IF NOT EXISTS 'unplanned_date'")

    # VACATION and UNPLANNED_DATE may never recur yearly as of this migration
    # (see RECURRING_ALLOWED_TYPES in app/models/special_event.py; BIRTHDAY,
    # WEDDING_ANNIVERSARY, ANNIVERSARY, and CUSTOM may all optionally recur) —
    # bring any existing VACATION rows saved before that rule existed into line.
    op.execute("UPDATE special_events SET recurs_yearly = false WHERE type = 'vacation' AND recurs_yearly = true")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE, and the recurs_yearly backfill
    # above is lossy (original per-row values aren't recorded anywhere). Revert
    # both by hand if this ever needs undoing — not a migration to run automatically.
    raise NotImplementedError("cannot drop an enum value in Postgres; downgrade manually if needed")
