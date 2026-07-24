"""add call_logs table

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("caller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("callee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("call_type", postgresql.ENUM("voice", "video", name="call_log_type"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("answered", "missed", "declined", "cancelled", name="call_log_status"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["caller_id"], ["users.id"], name="fk_call_logs_caller_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["callee_id"], ["users.id"], name="fk_call_logs_callee_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_call_logs"),
    )
    op.create_index("ix_call_logs_caller_id", "call_logs", ["caller_id"])
    op.create_index("ix_call_logs_callee_id", "call_logs", ["callee_id"])
    op.create_index("ix_call_logs_started_at", "call_logs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_call_logs_started_at", table_name="call_logs")
    op.drop_index("ix_call_logs_callee_id", table_name="call_logs")
    op.drop_index("ix_call_logs_caller_id", table_name="call_logs")
    op.drop_table("call_logs")
    postgresql.ENUM(name="call_log_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="call_log_type").drop(op.get_bind(), checkfirst=True)
