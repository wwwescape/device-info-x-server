"""add user timezone and last_birthday_notified_year

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("last_birthday_notified_year", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_birthday_notified_year")
    op.drop_column("users", "timezone")
