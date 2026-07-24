from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ClientEnvelope(BaseModel):
    """Inbound message from the app. `data` is intentionally untyped here —
    each handler in ws/router.py validates the shape it expects."""

    type: str
    id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


def build_envelope(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "data": data, "ts": datetime.now(UTC).isoformat()}
