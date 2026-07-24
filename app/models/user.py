import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    UNSPECIFIED = "unspecified"


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[Gender] = mapped_column(
        SAEnum(Gender, name="gender", values_callable=lambda e: [m.value for m in e]),
        default=Gender.UNSPECIFIED,
        server_default=Gender.UNSPECIFIED.value,
        nullable=False,
    )
    # Mandatory as of registration (see auth_service.register) — collected up front so a
    # recurring BIRTHDAY calendar event can be created the moment the account exists.
    birthday_date: Mapped[date] = mapped_column(Date, nullable=False)
    # use_alter breaks the users<->media_assets circular FK cycle: media_assets.owner_id
    # references users.id, so this constraint must be added after both tables exist.
    avatar_media_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "media_assets.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_users_avatar_media_id_media_assets",
        ),
        nullable=True,
    )
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Cooldown for the manual "I'm online" push (presence_service.send_online_ping) — 15 minutes
    # between sends, enforced server-side so it can't be bypassed by a client-only disabled button.
    last_online_ping_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # IANA id (e.g. "Asia/Kolkata"), auto-detected client-side and refreshed silently on every
    # login (see auth_service.issue_token_pair) — never asked for explicitly. Used by
    # app/tasks/scheduler.py's birthday sweep to compute each user's own local midnight.
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Dedup for the once-a-year birthday push — set the moment it fires, so a later sweep tick
    # the same year doesn't re-notify.
    last_birthday_notified_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Dedup for the two period-cycle pushes in app/tasks/scheduler.py — each stores the
    # *predicted* cycle_start_date already notified for (not a date the sweep ran), so a changed
    # prediction (e.g. a new cycle gets logged, shifting the forecast) naturally re-arms both
    # without an explicit reset. FEMALE-only in practice since the sweep only queries that gender,
    # but the columns themselves aren't gender-gated.
    last_period_upcoming_notified_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_period_not_logged_notified_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Authored by this user, shown on their *partner's* birthday popup (never their own) — see
    # ConsoleTabsViewModel.checkBirthday's doc comment client-side for why this is synced rather
    # than a local-only setting.
    birthday_message: Mapped[str | None] = mapped_column(String(75), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Set by `app.cli reset-password` (an admin-generated one-time password); cleared the moment
    # `auth_service.change_password` succeeds. Login itself never blocks on this — the client
    # detects it via `UserPublic.must_change_password` and gates entry to the console until a
    # real password is set, same "app enforces the gate" spirit as the local PIN.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
