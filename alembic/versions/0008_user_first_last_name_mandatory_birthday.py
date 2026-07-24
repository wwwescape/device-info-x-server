"""users: add first_name/last_name, make birthday_date mandatory

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No real accounts exist on this server yet (confirmed) — safe to add these NOT NULL with
    # no backfill, and to tighten birthday_date straight to NOT NULL.
    op.add_column("users", sa.Column("first_name", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("users", sa.Column("last_name", sa.String(length=128), nullable=False, server_default=""))
    op.alter_column("users", "first_name", server_default=None)
    op.alter_column("users", "last_name", server_default=None)
    op.alter_column("users", "birthday_date", existing_type=sa.Date(), nullable=False)


def downgrade() -> None:
    op.alter_column("users", "birthday_date", existing_type=sa.Date(), nullable=True)
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
