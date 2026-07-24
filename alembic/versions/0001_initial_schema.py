"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users -----------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        # avatar_media_id FK added later via ALTER — breaks the users<->media_assets cycle.
        sa.Column("avatar_media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["users.id"], name="fk_users_partner_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    # --- media_assets ------------------------------------------------------
    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "category",
            postgresql.ENUM(
                "message_image", "message_voice", "avatar", "locker_file", name="media_category"
            ),
            nullable=False,
        ),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_media_assets_owner_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_assets"),
    )
    op.create_index("ix_media_assets_owner_id", "media_assets", ["owner_id"])

    # Now that both tables exist, add the deferred users -> media_assets FK.
    op.create_foreign_key(
        "fk_users_avatar_media_id_media_assets",
        "users",
        "media_assets",
        ["avatar_media_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- partner_codes -----------------------------------------------------
    op.create_table(
        "partner_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("code_preview", sa.String(8), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_partner_codes_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_partner_codes"),
        sa.UniqueConstraint("code_hash", name="uq_partner_codes_code_hash"),
    )
    op.create_index("ix_partner_codes_user_id", "partner_codes", ["user_id"])

    # --- refresh_tokens ------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("device_label", sa.String(128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # --- devices -------------------------------------------------------------
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fcm_token", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_devices_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint("fcm_token", name="uq_devices_fcm_token"),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])

    # --- messages --------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM("text", "image", "voice", "system", name="message_type"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reply_to_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(body, ''))", persisted=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], name="fk_messages_sender_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media_assets.id"], name="fk_messages_media_id_media_assets", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"], ["messages.id"], name="fk_messages_reply_to_id_messages", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.UniqueConstraint("client_message_id", name="uq_messages_client_message_id"),
    )
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index("ix_messages_search_vector", "messages", ["search_vector"], postgresql_using="gin")

    # --- message_stars -------------------------------------------------------
    op.create_table(
        "message_stars",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_message_stars_message_id_messages", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_message_stars_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_stars"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_stars_message_id_user_id"),
    )
    op.create_index("ix_message_stars_message_id", "message_stars", ["message_id"])
    op.create_index("ix_message_stars_user_id", "message_stars", ["user_id"])

    # --- message_reactions -----------------------------------------------------
    op.create_table(
        "message_reactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_message_reactions_message_id_messages", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_message_reactions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_reactions"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_reactions_message_id_user_id"),
    )
    op.create_index("ix_message_reactions_message_id", "message_reactions", ["message_id"])
    op.create_index("ix_message_reactions_user_id", "message_reactions", ["user_id"])

    # --- calendar_events ---------------------------------------------------------
    op.create_table(
        "calendar_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("recurrence_rule", sa.String(255), nullable=True),
        sa.Column("recurrence_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_calendar_events_created_by_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_events"),
    )
    op.create_index("ix_calendar_events_created_by", "calendar_events", ["created_by"])
    op.create_index("ix_calendar_events_start_at", "calendar_events", ["start_at"])

    # --- calendar_event_reminders --------------------------------------------------
    op.create_table(
        "calendar_event_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("minutes_before", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["calendar_events.id"],
            name="fk_calendar_event_reminders_event_id_calendar_events",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_event_reminders"),
    )
    op.create_index("ix_calendar_event_reminders_event_id", "calendar_event_reminders", ["event_id"])

    # --- special_events -------------------------------------------------------------
    op.create_table(
        "special_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "birthday", "anniversary", "important_date", "custom", name="special_event_type"
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("recurs_yearly", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reminder_days_before", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_special_events_created_by_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_special_events"),
    )
    op.create_index("ix_special_events_created_by", "special_events", ["created_by"])
    op.create_index("ix_special_events_date", "special_events", ["date"])

    # --- reminder_deliveries -----------------------------------------------------------
    op.create_table(
        "reminder_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM("calendar_event", "special_event", name="reminder_source_type"),
            nullable=False,
        ),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurrence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minutes_before", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reminder_deliveries"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "occurrence_at",
            "minutes_before",
            name="uq_reminder_deliveries_source_occurrence_minutes",
        ),
    )
    op.create_index("ix_reminder_deliveries_source_id", "reminder_deliveries", ["source_id"])

    # --- period_cycles -------------------------------------------------------------------
    op.create_table(
        "period_cycles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_start_date", sa.Date(), nullable=False),
        sa.Column("cycle_length_days", sa.Integer(), nullable=True),
        sa.Column("period_length_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_period_cycles_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_period_cycles"),
    )
    op.create_index("ix_period_cycles_user_id", "period_cycles", ["user_id"])
    op.create_index("ix_period_cycles_cycle_start_date", "period_cycles", ["cycle_start_date"])

    # --- period_symptom_logs ---------------------------------------------------------------
    op.create_table(
        "period_symptom_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("symptoms", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "flow_intensity",
            postgresql.ENUM("light", "medium", "heavy", name="flow_intensity"),
            nullable=True,
        ),
        sa.Column("mood", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_period_symptom_logs_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_period_symptom_logs"),
        sa.UniqueConstraint("user_id", "log_date", name="uq_period_symptom_logs_user_id_log_date"),
    )
    op.create_index("ix_period_symptom_logs_user_id", "period_symptom_logs", ["user_id"])

    # --- locker_items --------------------------------------------------------------------
    op.create_table(
        "locker_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "category",
            postgresql.ENUM("document", "photo", "note", "other", name="locker_category"),
            nullable=False,
        ),
        sa.Column("is_encrypted", sa.Boolean(), nullable=False),
        sa.Column("encryption_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_locker_items_owner_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media_assets.id"], name="fk_locker_items_media_id_media_assets", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_locker_items"),
    )
    op.create_index("ix_locker_items_owner_id", "locker_items", ["owner_id"])


def downgrade() -> None:
    op.drop_table("locker_items")
    op.drop_table("period_symptom_logs")
    op.drop_table("period_cycles")
    op.drop_table("reminder_deliveries")
    op.drop_table("special_events")
    op.drop_table("calendar_event_reminders")
    op.drop_table("calendar_events")
    op.drop_table("message_reactions")
    op.drop_table("message_stars")
    op.drop_table("messages")
    op.drop_table("devices")
    op.drop_table("refresh_tokens")
    op.drop_table("partner_codes")
    op.drop_constraint("fk_users_avatar_media_id_media_assets", "users", type_="foreignkey")
    op.drop_table("media_assets")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_name in (
        "locker_category",
        "flow_intensity",
        "reminder_source_type",
        "special_event_type",
        "message_type",
        "media_category",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
