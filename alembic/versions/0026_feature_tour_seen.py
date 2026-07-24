"""add feature_tour_seen table

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_tour_seen",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tour_key", sa.String(length=64), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_feature_tour_seen_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feature_tour_seen"),
        sa.UniqueConstraint("user_id", "tour_key", name="uq_feature_tour_seen_user_tour"),
    )
    op.create_index("ix_feature_tour_seen_user_id", "feature_tour_seen", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_feature_tour_seen_user_id", table_name="feature_tour_seen")
    op.drop_table("feature_tour_seen")
