"""add media_assets.thumbnail_media_id

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("thumbnail_media_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_media_assets_thumbnail_media_id_media_assets",
        "media_assets",
        "media_assets",
        ["thumbnail_media_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_media_assets_thumbnail_media_id_media_assets", "media_assets", type_="foreignkey")
    op.drop_column("media_assets", "thumbnail_media_id")
