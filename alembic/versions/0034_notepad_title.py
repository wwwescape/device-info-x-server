"""add notepad_entries.title

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notepad_entries", sa.Column("title", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("notepad_entries", "title")
