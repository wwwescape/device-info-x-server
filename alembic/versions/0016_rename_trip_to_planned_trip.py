"""rename event_type 'trip' to 'planned_trip' and make it cancellable

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-06

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Renaming the enum label in place (rather than add-new/drop-old) automatically repoints
    # every existing calendar_events row that was 'trip' — no data backfill needed.
    op.execute("ALTER TYPE event_type RENAME VALUE 'trip' TO 'planned_trip'")


def downgrade() -> None:
    op.execute("ALTER TYPE event_type RENAME VALUE 'planned_trip' TO 'trip'")
