"""add whats_new_seen table

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whats_new_seen",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_whats_new_seen_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_whats_new_seen"),
        sa.UniqueConstraint("user_id", "tag", name="uq_whats_new_seen_user_tag"),
    )
    op.create_index("ix_whats_new_seen_user_id", "whats_new_seen", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_whats_new_seen_user_id", table_name="whats_new_seen")
    op.drop_table("whats_new_seen")
