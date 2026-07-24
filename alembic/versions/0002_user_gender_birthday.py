"""user gender + birthday_date

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    gender = postgresql.ENUM("male", "female", "unspecified", name="gender")
    gender.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column("gender", gender, server_default="unspecified", nullable=False),
    )
    op.add_column("users", sa.Column("birthday_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "birthday_date")
    op.drop_column("users", "gender")
    postgresql.ENUM(name="gender").drop(op.get_bind(), checkfirst=True)
