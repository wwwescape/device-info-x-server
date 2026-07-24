"""add intimacy_logs table

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intimacy_logs",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("initiated_by", sa.String(length=64), nullable=True),
        sa.Column("protection_used", sa.Boolean(), nullable=True),
        sa.Column("positions", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("locations", postgresql.ARRAY(sa.String()), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["calendar_events.id"], name="fk_intimacy_logs_event_id_calendar_events", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_intimacy_logs"),
    )


def downgrade() -> None:
    op.drop_table("intimacy_logs")
