"""add media_group_id column to messages

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("media_group_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_messages_media_group_id", "messages", ["media_group_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_media_group_id", table_name="messages")
    op.drop_column("messages", "media_group_id")
