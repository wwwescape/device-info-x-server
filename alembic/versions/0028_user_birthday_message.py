"""add users.birthday_message

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birthday_message", sa.String(length=75), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "birthday_message")
