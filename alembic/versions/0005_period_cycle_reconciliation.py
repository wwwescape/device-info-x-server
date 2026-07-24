"""period tracking: fold symptom logs into per-cycle rows

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-26

Reconciles the server's period model with Android's CycleEntryEntity
(one row per cycle, not a separate daily log). period_length_days is
replaced by an explicit period_end_date; symptoms/flow_intensity move
onto period_cycles; period_symptom_logs (including its `mood` field,
which Android has no concept of) is dropped outright.

This is destructive: any existing period_symptom_logs rows and the
period_length_days values on period_cycles are not migrated forward,
per the decision recorded in SERVER_PHASES.md Phase S6.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("period_cycles", sa.Column("period_end_date", sa.Date(), nullable=True))
    op.add_column(
        "period_cycles",
        sa.Column("symptoms", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
    )
    op.add_column(
        "period_cycles",
        sa.Column(
            "flow_intensity",
            postgresql.ENUM("light", "medium", "heavy", name="flow_intensity", create_type=False),
            nullable=True,
        ),
    )
    op.drop_column("period_cycles", "period_length_days")
    op.drop_table("period_symptom_logs")


def downgrade() -> None:
    op.create_table(
        "period_symptom_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("symptoms", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "flow_intensity",
            postgresql.ENUM("light", "medium", "heavy", name="flow_intensity", create_type=False),
            nullable=True,
        ),
        sa.Column("mood", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_period_symptom_logs_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_period_symptom_logs"),
        sa.UniqueConstraint("user_id", "log_date", name="uq_period_symptom_logs_user_id_log_date"),
    )
    op.create_index("ix_period_symptom_logs_user_id", "period_symptom_logs", ["user_id"])

    op.add_column("period_cycles", sa.Column("period_length_days", sa.Integer(), nullable=True))
    op.drop_column("period_cycles", "flow_intensity")
    op.drop_column("period_cycles", "symptoms")
    op.drop_column("period_cycles", "period_end_date")
