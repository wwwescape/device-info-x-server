"""add calendar_events.cover_media_id

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column("cover_media_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_calendar_events_cover_media_id_media_assets",
        "calendar_events",
        "media_assets",
        ["cover_media_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_calendar_events_cover_media_id_media_assets", "calendar_events", type_="foreignkey")
    op.drop_column("calendar_events", "cover_media_id")
