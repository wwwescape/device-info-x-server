"""add app_release table

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_release",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("build_timestamp", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_app_release"),
    )


def downgrade() -> None:
    op.drop_table("app_release")
