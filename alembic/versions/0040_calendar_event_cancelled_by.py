"""add cancelled_by column to calendar_events

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("cancelled_by", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_events", "cancelled_by")
