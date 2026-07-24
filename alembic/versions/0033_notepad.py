"""add notepad: notepad_entries table (private/shared free-text notes)

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notepad_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("type", postgresql.ENUM("private", "shared", name="notepad_entry_type"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_notepad_entries_owner_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name="fk_notepad_entries_updated_by_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notepad_entries"),
    )
    op.create_index("ix_notepad_entries_owner_id", "notepad_entries", ["owner_id"])
    op.create_index("ix_notepad_entries_type", "notepad_entries", ["type"])


def downgrade() -> None:
    op.drop_table("notepad_entries")
    postgresql.ENUM(name="notepad_entry_type").drop(op.get_bind(), checkfirst=True)
