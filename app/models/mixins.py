import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        # onupdate uses clock_timestamp(), not now(): now()/CURRENT_TIMESTAMP is frozen at the
        # transaction's start time in Postgres, so two updates inside the same transaction (as
        # happens under the test suite's one-transaction-per-test isolation, see conftest.py)
        # would otherwise get an identical updated_at — silently defeating any optimistic-
        # concurrency check built on this column (see NotepadEntry). clock_timestamp() gives the
        # true per-statement time instead.
        DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp(), nullable=False
    )
