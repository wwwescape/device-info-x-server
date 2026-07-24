"""add updated_at column to messages

Backs GET /messages?changed_after=... (offline catch-up for deletes/restores/edits) and the
client's stale-write guard. Backfilled from the newest timestamp each row already carries.

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "UPDATE messages SET updated_at = GREATEST(created_at, COALESCE(edited_at, created_at), "
        "COALESCE(deleted_at, created_at), COALESCE(read_at, created_at), COALESCE(delivered_at, created_at), "
        "COALESCE(pinned_at, created_at))"
    )
    op.create_index("ix_messages_updated_at", "messages", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_updated_at", table_name="messages")
    op.drop_column("messages", "updated_at")
