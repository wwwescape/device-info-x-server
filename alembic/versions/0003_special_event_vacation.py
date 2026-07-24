"""special_event_type: add VACATION

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-26

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic wraps
    # migrations in by default, so it needs its own autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE special_event_type ADD VALUE IF NOT EXISTS 'vacation'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Reverting requires recreating
    # the enum type and remapping any rows using 'vacation', which isn't a
    # migration to run automatically — do it by hand if this ever needs undoing.
    raise NotImplementedError("cannot drop an enum value in Postgres; downgrade manually if needed")
