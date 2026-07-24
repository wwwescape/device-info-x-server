"""add location: message_type 'location' value, messages.location_lat/location_lng

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic wraps migrations in by
    # default, so it needs its own autocommit block — see 0032's identical treatment.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE message_type ADD VALUE IF NOT EXISTS 'location'")

    op.add_column("messages", sa.Column("location_lat", sa.Float(), nullable=True))
    op.add_column("messages", sa.Column("location_lng", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "location_lng")
    op.drop_column("messages", "location_lat")
    # Postgres has no ALTER TYPE ... DROP VALUE — see 0032's identical downgrade note.
    raise NotImplementedError("cannot drop an enum value in Postgres; downgrade manually if needed")
