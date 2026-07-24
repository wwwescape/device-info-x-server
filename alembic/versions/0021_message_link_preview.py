"""add link preview columns to messages, message_link_preview media category

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic wraps migrations in by
    # default, so it needs its own autocommit block — same reasoning as 0006_video_support.py.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE media_category ADD VALUE IF NOT EXISTS 'message_link_preview'")

    op.add_column("messages", sa.Column("link_preview_url", sa.String(length=2048), nullable=True))
    op.add_column("messages", sa.Column("link_preview_title", sa.String(length=512), nullable=True))
    op.add_column("messages", sa.Column("link_preview_description", sa.Text(), nullable=True))
    op.add_column(
        "messages",
        sa.Column("link_preview_media_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_messages_link_preview_media_id_media_assets",
        "messages",
        "media_assets",
        ["link_preview_media_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE, so this migration can't be automatically
    # reverted end-to-end (same reasoning as 0006_video_support.py) — raising immediately, before
    # touching anything, keeps this a safe no-op to retry rather than leaving the columns dropped
    # but the enum value stranded. To undo by hand: drop the 4 columns/FK added in upgrade(), then
    # recreate the media_category enum type without 'message_link_preview' and remap any rows.
    raise NotImplementedError("cannot drop an enum value in Postgres; downgrade manually if needed")
