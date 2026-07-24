"""locker albums + item favorites

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- locker_albums ---------------------------------------------------------
    op.create_table(
        "locker_albums",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_locker_albums_owner_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_locker_albums"),
    )
    op.create_index("ix_locker_albums_owner_id", "locker_albums", ["owner_id"])

    # --- locker_items: album_id + is_favorite -----------------------------------
    op.add_column("locker_items", sa.Column("album_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_locker_items_album_id_locker_albums",
        "locker_items",
        "locker_albums",
        ["album_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_locker_items_album_id", "locker_items", ["album_id"])
    op.add_column(
        "locker_items",
        sa.Column("is_favorite", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("locker_items", "is_favorite")
    op.drop_index("ix_locker_items_album_id", table_name="locker_items")
    op.drop_constraint("fk_locker_items_album_id_locker_albums", "locker_items", type_="foreignkey")
    op.drop_column("locker_items", "album_id")
    op.drop_table("locker_albums")
