"""add period notification dedup columns to users

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_period_upcoming_notified_for", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("last_period_not_logged_notified_for", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_period_not_logged_notified_for")
    op.drop_column("users", "last_period_upcoming_notified_for")
