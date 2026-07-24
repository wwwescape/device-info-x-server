"""add cancellation_reason column to calendar_events

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("cancellation_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_events", "cancellation_reason")
