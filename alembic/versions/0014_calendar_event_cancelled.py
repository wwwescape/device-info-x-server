"""add cancelled column to calendar_events

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("calendar_events", "cancelled", server_default=None)


def downgrade() -> None:
    op.drop_column("calendar_events", "cancelled")
