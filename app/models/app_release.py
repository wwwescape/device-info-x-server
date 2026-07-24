from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class AppRelease(UUIDPrimaryKeyMixin, Base):
    """Which build the client should consider "latest" — a single row, not a history table (see
    the TODOS.md writeup this was built from). `release_service` is what actually enforces the
    one-row invariant (updates the existing row in place if present, only inserts if the table is
    still empty); nothing at the schema level stops a second row from existing, since there's no
    natural unique key to constrain on for a table that's just one arbitrary value.

    `build_timestamp` deliberately isn't a real timestamp column — it's a plain, human-readable
    string set by hand (e.g. "2026-08-15-2144") right before publishing a build, matching the
    client's own `BuildConfig.BUILD_TIMESTAMP` byte-for-byte. Compared for plain string equality
    client-side, never parsed or ordered."""

    __tablename__ = "app_release"

    build_timestamp: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
