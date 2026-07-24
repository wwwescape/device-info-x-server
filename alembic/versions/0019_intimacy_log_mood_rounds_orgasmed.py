"""add moods, rounds, orgasmed_by columns to intimacy_logs

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "intimacy_logs",
        sa.Column("moods", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.add_column("intimacy_logs", sa.Column("rounds", sa.Integer(), nullable=True))
    op.add_column("intimacy_logs", sa.Column("orgasmed_by", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("intimacy_logs", "orgasmed_by")
    op.drop_column("intimacy_logs", "rounds")
    op.drop_column("intimacy_logs", "moods")
