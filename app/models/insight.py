import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class Insight(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A single "DIX AI" insight — a manually-authored one-liner, managed entirely through the CLI
    (`add-insight`/`list-insights`/`delete-insight`/`enable-insight`/`disable-insight`), not the
    client. Unlike What's New (bullet copy ships in the client, only seen-state lives server-side),
    an Insight's [text] lives here — DIX AI isn't real AI yet, so a human writes the copy and is
    responsible for its correctness, same framing as this module's own `cli.py`'s "no admin/role
    concept, private 2-account app" precedent.

    [target_user_id] is optional: null means visible to both accounts (global, like What's New);
    set means visible to that one account only — there's no pair-scoping concept, since a server
    only ever has the 2 accounts and "targeted" just means "the other one doesn't see it" — see
    `insight_repo.list_visible_to` for the exact rule. `ondelete="CASCADE"` here means a targeted
    insight is deleted outright if its target account is deleted, rather than orphaned into a
    global one.

    [enabled] is a separate, orthogonal axis from per-user seen-state (`InsightSeen`): disabling an
    insight stops it being *offered* to anyone who hasn't seen it yet, but doesn't retroactively
    un-show it from someone who already has. Letting an already-seen insight show again for someone
    is `InsightSeen`'s job (`insight_seen_repo.reset_seen_for_user`/`reset_seen_for_all`, the CLI's
    `reset-insight-seen`), not this flag's."""

    __tablename__ = "insights"

    text: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
