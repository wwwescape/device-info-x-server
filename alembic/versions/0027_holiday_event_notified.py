"""add holiday_event_notified table

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "holiday_event_notified",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_holiday_event_notified_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_holiday_event_notified"),
        sa.UniqueConstraint("user_id", "event_name", "event_date", name="uq_holiday_event_notified_user_event_date"),
    )
    op.create_index("ix_holiday_event_notified_user_id", "holiday_event_notified", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_holiday_event_notified_user_id", table_name="holiday_event_notified")
    op.drop_table("holiday_event_notified")
