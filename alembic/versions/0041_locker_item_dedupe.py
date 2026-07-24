"""add locker item source columns and dedupe unique indexes

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("locker_items", sa.Column("original_message_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("locker_items", sa.Column("original_event_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "locker_items", sa.Column("original_attachment_media_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    # Partial: only enforced when the item was actually saved from a message/event attachment
    # (a direct gallery/document import leaves these null and is never deduped), and excludes
    # soft-deleted rows so saving, deleting, then re-saving the same attachment later doesn't
    # spuriously conflict with the deleted row.
    op.create_index(
        "uq_locker_items_owner_message",
        "locker_items",
        ["owner_id", "original_message_id"],
        unique=True,
        postgresql_where=sa.text("original_message_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_locker_items_owner_event_media",
        "locker_items",
        ["owner_id", "original_event_id", "original_attachment_media_id"],
        unique=True,
        postgresql_where=sa.text(
            "original_event_id IS NOT NULL AND original_attachment_media_id IS NOT NULL AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_locker_items_owner_event_media", table_name="locker_items")
    op.drop_index("uq_locker_items_owner_message", table_name="locker_items")
    op.drop_column("locker_items", "original_attachment_media_id")
    op.drop_column("locker_items", "original_event_id")
    op.drop_column("locker_items", "original_message_id")
