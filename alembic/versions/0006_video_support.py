"""add video support: message_type, media_category, locker_category

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-01

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic wraps
    # migrations in by default, so it needs its own autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE message_type ADD VALUE IF NOT EXISTS 'video'")
        op.execute("ALTER TYPE media_category ADD VALUE IF NOT EXISTS 'message_video'")
        op.execute("ALTER TYPE locker_category ADD VALUE IF NOT EXISTS 'video'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Reverting requires recreating
    # each enum type and remapping any rows using the new values, which isn't
    # a migration to run automatically — do it by hand if this ever needs undoing.
    raise NotImplementedError("cannot drop an enum value in Postgres; downgrade manually if needed")
