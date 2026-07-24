"""add polls: message_type 'poll' value, messages.poll_allows_multiple/poll_closed_at,
poll_options and poll_votes tables

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic wraps migrations in by
    # default, so it needs its own autocommit block — see 0025's identical treatment.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE message_type ADD VALUE IF NOT EXISTS 'poll'")

    op.add_column(
        "messages",
        sa.Column("poll_allows_multiple", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("messages", sa.Column("poll_closed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "poll_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_text", sa.String(length=200), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_poll_options_message_id_messages", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_poll_options"),
    )
    op.create_index("ix_poll_options_message_id", "poll_options", ["message_id"])

    op.create_table(
        "poll_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["option_id"], ["poll_options.id"], name="fk_poll_votes_option_id_poll_options", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_poll_votes_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_poll_votes"),
        sa.UniqueConstraint("option_id", "user_id", name="uq_poll_votes_option_id_user_id"),
    )
    op.create_index("ix_poll_votes_option_id", "poll_votes", ["option_id"])
    op.create_index("ix_poll_votes_user_id", "poll_votes", ["user_id"])


def downgrade() -> None:
    op.drop_table("poll_votes")
    op.drop_table("poll_options")
    op.drop_column("messages", "poll_closed_at")
    op.drop_column("messages", "poll_allows_multiple")
    # Postgres has no ALTER TYPE ... DROP VALUE — see 0025's identical downgrade note.
    raise NotImplementedError("cannot drop an enum value in Postgres; downgrade manually if needed")
