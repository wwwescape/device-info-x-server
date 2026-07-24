"""add insights and insight_seen tables

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name="fk_insights_target_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_insights"),
    )
    op.create_index("ix_insights_target_user_id", "insights", ["target_user_id"])

    op.create_table(
        "insight_seen",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("insight_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_insight_seen_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["insight_id"],
            ["insights.id"],
            name="fk_insight_seen_insight_id_insights",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_insight_seen"),
        sa.UniqueConstraint("user_id", "insight_id", name="uq_insight_seen_user_insight"),
    )
    op.create_index("ix_insight_seen_user_id", "insight_seen", ["user_id"])
    op.create_index("ix_insight_seen_insight_id", "insight_seen", ["insight_id"])


def downgrade() -> None:
    op.drop_index("ix_insight_seen_insight_id", table_name="insight_seen")
    op.drop_index("ix_insight_seen_user_id", table_name="insight_seen")
    op.drop_table("insight_seen")
    op.drop_index("ix_insights_target_user_id", table_name="insights")
    op.drop_table("insights")
