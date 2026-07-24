"""unify calendar_events and special_events into one typed table

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No real account data exists yet (confirmed) — this is a clean-slate merge, not a
    # data-preserving transform. special_events is dropped outright rather than migrated.
    event_type = postgresql.ENUM(
        "birthday",
        "wedding_anniversary",
        "anniversary",
        "vacation",
        "trip",
        "planned_date",
        "unplanned_date",
        "planned_drive",
        "unplanned_drive",
        "reminder",
        "custom",
        name="event_type",
    )
    event_type.create(op.get_bind(), checkfirst=True)
    op.add_column("calendar_events", sa.Column("type", event_type, nullable=False))

    op.drop_table("special_events")
    postgresql.ENUM(name="special_event_type").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Recreating special_events (and backfilling calendar_events rows that used to live there)
    # isn't a migration to run automatically — do it by hand if this ever needs undoing.
    raise NotImplementedError("cannot cleanly split the unified table back apart; downgrade manually if needed")
