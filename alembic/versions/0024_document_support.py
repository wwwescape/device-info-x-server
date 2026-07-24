"""add document support: message_type, media_category

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-09

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic wraps
    # migrations in by default, so it needs its own autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE message_type ADD VALUE IF NOT EXISTS 'document'")
        op.execute("ALTER TYPE media_category ADD VALUE IF NOT EXISTS 'message_document'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Reverting requires recreating
    # each enum type and remapping any rows using the new values, which isn't
    # a migration to run automatically — do it by hand if this ever needs undoing.
    raise NotImplementedError("cannot drop an enum value in Postgres; downgrade manually if needed")
