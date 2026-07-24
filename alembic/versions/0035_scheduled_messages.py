"""add scheduled_messages table (staged messages awaiting delivery)

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sender_id"], ["users.id"], name="fk_scheduled_messages_sender_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scheduled_messages"),
    )
    op.create_index("ix_scheduled_messages_sender_id", "scheduled_messages", ["sender_id"])
    op.create_index("ix_scheduled_messages_scheduled_at", "scheduled_messages", ["scheduled_at"])


def downgrade() -> None:
    op.drop_table("scheduled_messages")
