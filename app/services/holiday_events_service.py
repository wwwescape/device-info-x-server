import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_EVENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "events.json"


@dataclass(frozen=True)
class HolidayEvent:
    name: str
    date: date
    wishes: str


_cache: list[HolidayEvent] | None = None


def load_events() -> list[HolidayEvent]:
    """`app/data/events.json` — the server's own copy of the client's `res/raw/events.json`
    (`HolidayEventsRepository`'s own doc comment explains why there are two: small, static
    reference data that's simplest kept in sync by hand rather than adding an endpoint for
    something that only changes once a year). Parsed once and cached for the process lifetime — a
    couple dozen small entries, no reason to re-read the file on every sweep tick. A malformed
    file logs a warning and disables the holiday-event push for this process rather than crashing
    the scheduler — same "a missed greeting is a minor miss" reasoning the client side uses."""
    global _cache
    if _cache is not None:
        return _cache

    try:
        raw = json.loads(_EVENTS_PATH.read_text(encoding="utf-8"))
        events = []
        for entry in raw:
            try:
                events.append(
                    HolidayEvent(
                        name=entry["name"],
                        date=date.fromisoformat(entry["date"]),
                        wishes=entry["wishes"],
                    )
                )
            except (KeyError, ValueError):
                logger.warning("skipping malformed events.json entry: %r", entry)
        _cache = events
    except (OSError, json.JSONDecodeError):
        logger.warning("failed to load %s — holiday-event push disabled this process", _EVENTS_PATH, exc_info=True)
        _cache = []

    return _cache
