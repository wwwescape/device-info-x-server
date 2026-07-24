"""add calendar event attachments: media_category values, calendar_event_attachments table

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic wraps
    # migrations in by default, so it needs its own autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE media_category ADD VALUE IF NOT EXISTS 'calendar_image'")
        op.execute("ALTER TYPE media_category ADD VALUE IF NOT EXISTS 'calendar_video'")
        op.execute("ALTER TYPE media_category ADD VALUE IF NOT EXISTS 'calendar_document'")

    op.create_table(
        "calendar_event_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["calendar_events.id"],
            name="fk_calendar_event_attachments_event_id_calendar_events",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media_assets.id"],
            name="fk_calendar_event_attachments_media_id_media_assets",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_event_attachments"),
    )
    op.create_index("ix_calendar_event_attachments_event_id", "calendar_event_attachments", ["event_id"])


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Reverting requires recreating
    # each enum type and remapping any rows using the new values, which isn't
    # a migration to run automatically — do it by hand if this ever needs undoing.
    raise NotImplementedError("cannot drop an enum value in Postgres; downgrade manually if needed")
