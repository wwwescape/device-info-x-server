"""One-off maintenance commands, run via `docker exec <api-container> python -m app.cli <command>`.

Not exposed over HTTP — kept out-of-band on purpose since there's no admin/role
concept in the data model (this is a private, 2-account app; see auth_service.MAX_ACCOUNTS).
"""

import argparse
import asyncio
import csv
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from getpass import getpass
from pathlib import Path

from dateutil.rrule import rrulestr
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import text

import app.models  # noqa: F401  # registers every model on Base.metadata before we read it
from app.core.config import get_settings
from app.core.exceptions import DomainError
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.integrations import fcm
from app.models.calendar_event import CANCELLABLE_TYPES, RECURRING_ALLOWED_TYPES, CalendarEvent
from app.models.period import PeriodCycle
from app.repositories import calendar_repo, device_repo, period_repo, user_repo
from app.schemas.auth import RegisterRequest
from app.schemas.calendar import CalendarEventCreate
from app.schemas.period import PeriodCycleCreate
from app.services import auth_service

# The CalendarEvent columns a CSV row fully controls — excludes reminder_minutes_before (a
# separate table, handled via calendar_repo.set_reminders) and intimacy (not supported by the
# CSV format at all, so an update must never touch it).
_CALENDAR_EVENT_FIELDS = (
    "type",
    "title",
    "description",
    "start_at",
    "end_at",
    "all_day",
    "location",
    "recurrence_rule",
    "recurrence_end_at",
    "color",
    "cancelled",
    "cancellation_reason",
)

settings = get_settings()


async def _truncate_all_tables() -> list[str]:
    table_names = [table.fullname for table in Base.metadata.sorted_tables]
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE"))
    return table_names


def _wipe_media() -> None:
    media_root = Path(settings.media_root)
    if not media_root.exists():
        return
    for entry in media_root.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


async def reset_all(*, skip_confirm: bool) -> None:
    if not skip_confirm:
        answer = input(
            "This permanently deletes ALL data (both accounts, pairing, messages, calendar, "
            "period tracking, locker, media files) and immediately signs both accounts out.\n"
            "This cannot be undone. Type RESET to continue: "
        )
        if answer != "RESET":
            print("Aborted — no changes made.")
            return

    tables = await _truncate_all_tables()
    _wipe_media()
    await engine.dispose()

    print(f"Wiped {len(tables)} tables and all media files under {settings.media_root}.")
    print("Both accounts are gone — re-register with SERVER_SETUP_TOKEN to recreate them.")


async def reset_password(*, username: str) -> None:
    """Forgotten-account-password recovery — generates a one-time password and prints it for the
    operator to relay to the account owner out of band (it's never stored anywhere, and this
    command never logs it to a file). See `auth_service.admin_reset_password` for what actually
    happens: every existing session is signed out, and the account is flagged so the app forces a
    real password to be set the moment this OTP is used to log in."""
    async with async_session_factory() as db:
        user = await user_repo.get_by_username(db, username)
        if user is None:
            print(f"No user named {username!r}.")
            return
        otp = await auth_service.admin_reset_password(db, user)

    print(f"One-time password for {username!r}: {otp}")
    print("Share this with them directly (call, text, in person) — it only works once.")
    print("They'll be required to set a real password the moment they log in with it.")
    print("Every device previously signed in to this account has been signed out.")


_REGISTER_FIELDS = (
    ("username", "Username (3-64 chars: letters, digits, . _ - only)"),
    ("display_name", "Display name (shown to their partner)"),
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("gender", "Gender (male / female / unspecified)"),
    ("birthday_date", "Birthday (YYYY-MM-DD)"),
)


def _prompt(label: str) -> str:
    return input(f"{label}: ").strip()


def _prompt_password() -> str:
    """Typed twice, hidden, so a non-technical operator can't silently create an account with a
    typo'd password they'll then have to reset."""
    while True:
        first = getpass("Password (min 8 characters, hidden as you type): ")
        second = getpass("Confirm password: ")
        if first != second:
            print("Passwords didn't match — try again.\n")
            continue
        return first


async def register() -> None:
    """Interactive account creation for an operator to run on the partner's behalf — reprompts
    per-field on validation failure instead of surfacing the raw error the HTTP endpoint would
    (a 422 with no context, which is what prompted this command to exist)."""
    if not settings.server_setup_token:
        print("SERVER_SETUP_TOKEN is not set on this server — registration is disabled until it is.")
        return

    print("Register a new account. Press Ctrl+C at any time to cancel.\n")

    data: dict[str, str] = {}
    try:
        for field, label in _REGISTER_FIELDS:
            data[field] = _prompt(label)
        data["password"] = _prompt_password()
    except KeyboardInterrupt:
        print("\nAborted — no changes made.")
        return
    data["setup_token"] = settings.server_setup_token

    while True:
        try:
            payload = RegisterRequest(**data)
            break
        except PydanticValidationError as exc:
            first_error = exc.errors()[0]
            field = str(first_error["loc"][0])
            print(f"\n{field}: {first_error['msg']}")
            label = next((lbl for f, lbl in _REGISTER_FIELDS if f == field), field)
            try:
                data[field] = _prompt_password() if field == "password" else _prompt(label)
            except KeyboardInterrupt:
                print("\nAborted — no changes made.")
                return

    print(
        f"\nAbout to create: {payload.username!r} — {payload.first_name} {payload.last_name}, "
        f"{payload.gender.value}, born {payload.birthday_date}."
    )
    try:
        answer = input("Type YES to create this account: ")
    except KeyboardInterrupt:
        answer = ""
    if answer != "YES":
        print("Aborted — no changes made.")
        return

    async with async_session_factory() as db:
        try:
            user = await auth_service.register(
                db,
                username=payload.username,
                password=payload.password,
                display_name=payload.display_name,
                first_name=payload.first_name,
                last_name=payload.last_name,
                gender=payload.gender,
                birthday_date=payload.birthday_date,
                setup_token=payload.setup_token,
            )
        except DomainError as exc:
            print(f"\nFailed: {exc.detail}")
            return

    print(f"\nAccount created: {user.username!r} (id {user.id}).")


DEFAULT_ACTIVE_WITHIN_DAYS = 30


async def test_notification(*, username: str) -> None:
    """Sends a real push (not the app's usual data-only messages) straight to the user's
    registered FCM tokens, so the OS displays it regardless of the Android app's own
    notification logic. The only write this can make is pruning tokens FCM itself reports as
    dead — never touches messages, calendar events, or period data."""
    fcm.init_firebase()
    async with async_session_factory() as db:
        user = await user_repo.get_by_username(db, username)
        if user is None:
            print(f"No user named {username!r}.")
            return
        user_id = user.id

    print(await fcm.send_test_notification(user_id))


async def list_devices(*, username: str, active_within_days: int, count_only: bool) -> None:
    """Read-only: lists the FCM tokens registered for a user, most recently active first. Tokens
    rotate (reinstall, cleared app data, Play Services refresh) and old rows are only pruned once
    a real push against them fails — so a stale-looking entry here just means an old install that
    was never cleaned up, not necessarily a problem. "Active" here just means last_active_at (set
    when the app registers its token, e.g. on login/launch) falls within active_within_days — the
    codebase has no other notion of device staleness to draw on."""
    async with async_session_factory() as db:
        user = await user_repo.get_by_username(db, username)
        if user is None:
            print(f"No user named {username!r}.")
            return
        devices = await device_repo.list_for_user(db, user.id)

    cutoff = datetime.now(UTC) - timedelta(days=active_within_days)
    active_count = sum(1 for d in devices if d.last_active_at is not None and d.last_active_at >= cutoff)

    if count_only:
        print(active_count)
        return

    if not devices:
        print(f"No registered devices for {username!r}.")
        return

    for device in devices:
        last_active = device.last_active_at.isoformat() if device.last_active_at else "never"
        print(
            f"...{device.fcm_token[-8:]}  platform={device.platform}  "
            f"app_version={device.app_version or 'unknown'}  last_active={last_active}"
        )
    print(
        f"\n{active_count} of {len(devices)} device(s) for {username!r} "
        f"active in the last {active_within_days} day(s)."
    )


def _read_csv_rows(file_path: Path) -> list[tuple[int, dict[str, str]]]:
    """Row 2 is the first data row (row 1 is the header). Blank cells are dropped entirely so
    optional fields fall back to their schema default instead of an empty string."""
    with file_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [
            (line_no, {k: v for k, v in row.items() if v not in (None, "")})
            for line_no, row in enumerate(reader, start=2)
        ]


def _format_validation_error(line_no: int, exc: PydanticValidationError) -> str:
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"]) or "row"
    return f"row {line_no}: {field}: {first['msg']}"


def _pop_row_id(data: dict[str, str], line_no: int, errors: list[str]) -> uuid.UUID | None:
    """A blank/absent `id` column means "create a new row"; a non-blank one that doesn't parse
    as a UUID is a row error, same severity as a schema validation failure."""
    raw_id = data.pop("id", None)
    if not raw_id:
        return None
    try:
        return uuid.UUID(raw_id)
    except ValueError:
        errors.append(f"row {line_no}: id: {raw_id!r} is not a valid UUID")
        return None


def _parse_period_rows(
    file_path: Path,
) -> tuple[list[tuple[int, uuid.UUID | None, PeriodCycleCreate]], list[str]]:
    parsed: list[tuple[int, uuid.UUID | None, PeriodCycleCreate]] = []
    errors: list[str] = []
    for line_no, data in _read_csv_rows(file_path):
        error_count_before = len(errors)
        row_id = _pop_row_id(data, line_no, errors)
        if row_id is None and len(errors) > error_count_before:
            continue  # bad id — already recorded, don't also validate the rest of the row
        # symptoms is a list column — pydantic won't split a delimited string on its own.
        if "symptoms" in data:
            data["symptoms"] = [s.strip() for s in data["symptoms"].split(";") if s.strip()]
        try:
            parsed.append((line_no, row_id, PeriodCycleCreate(**data)))
        except PydanticValidationError as exc:
            errors.append(_format_validation_error(line_no, exc))
    return parsed, errors


def _parse_calendar_rows(
    file_path: Path,
) -> tuple[list[tuple[int, uuid.UUID | None, CalendarEventCreate]], list[str]]:
    parsed: list[tuple[int, uuid.UUID | None, CalendarEventCreate]] = []
    errors: list[str] = []
    for line_no, data in _read_csv_rows(file_path):
        error_count_before = len(errors)
        row_id = _pop_row_id(data, line_no, errors)
        if row_id is None and len(errors) > error_count_before:
            continue  # bad id — already recorded, don't also validate the rest of the row
        data.pop("created_by", None)  # export-only column, never applied on import
        if "reminder_minutes_before" in data:
            data["reminder_minutes_before"] = [
                int(m.strip()) for m in data["reminder_minutes_before"].split(";") if m.strip()
            ]
        try:
            payload = CalendarEventCreate(**data)
        except PydanticValidationError as exc:
            errors.append(_format_validation_error(line_no, exc))
            continue

        # Mirrors calendar_service's create_event validation (_validate_rrule /
        # _validate_recurrence_allowed / _validate_cancelled_allowed) — duplicated here rather
        # than reused because importing goes through calendar_repo directly, not calendar_service,
        # so it never fires the per-event partner notification that create_event sends
        # (undesirable for a bulk/backfill import of historical events).
        if payload.recurrence_rule:
            try:
                rrulestr(payload.recurrence_rule, dtstart=payload.start_at)
            except (ValueError, TypeError) as exc:
                errors.append(f"row {line_no}: invalid recurrence_rule: {exc}")
                continue
            if payload.type not in RECURRING_ALLOWED_TYPES:
                errors.append(f"row {line_no}: {payload.type.value} events cannot recur")
                continue

        if payload.cancelled and payload.type not in CANCELLABLE_TYPES:
            errors.append(f"row {line_no}: {payload.type.value} events cannot be cancelled")
            continue
        if payload.cancellation_reason and not payload.cancelled:
            errors.append(f"row {line_no}: cancellation_reason requires cancelled=true")
            continue

        parsed.append((line_no, row_id, payload))
    return parsed, errors


async def export_period(*, file_path: Path, username: str) -> None:
    async with async_session_factory() as db:
        user = await user_repo.get_by_username(db, username)
        if user is None:
            print(f"No user named {username!r}.")
            return
        cycles = await period_repo.list_cycles(db, user.id)

    with file_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["id", "cycle_start_date", "cycle_length_days", "period_end_date", "symptoms", "flow_intensity", "notes"]
        )
        for cycle in cycles:
            writer.writerow(
                [
                    cycle.id,
                    cycle.cycle_start_date.isoformat(),
                    cycle.cycle_length_days if cycle.cycle_length_days is not None else "",
                    cycle.period_end_date.isoformat() if cycle.period_end_date else "",
                    ";".join(cycle.symptoms),
                    cycle.flow_intensity.value if cycle.flow_intensity else "",
                    cycle.notes or "",
                ]
            )
    print(f"Exported {len(cycles)} period cycle row(s) for {username!r} to {file_path}.")


async def export_calendar(*, file_path: Path) -> None:
    async with async_session_factory() as db:
        events = await calendar_repo.list_all(db)
        reminders = await calendar_repo.reminders_for_events(db, [event.id for event in events])
        usernames: dict[uuid.UUID, str] = {}
        for creator_id in {event.created_by for event in events}:
            creator = await user_repo.get_by_id(db, creator_id)
            usernames[creator_id] = creator.username if creator else ""

    with file_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "id",
                "type",
                "title",
                "description",
                "start_at",
                "end_at",
                "all_day",
                "location",
                "recurrence_rule",
                "recurrence_end_at",
                "color",
                "cancelled",
                "cancellation_reason",
                "reminder_minutes_before",
                "created_by",
            ]
        )
        for event in events:
            writer.writerow(
                [
                    event.id,
                    event.type.value,
                    event.title,
                    event.description or "",
                    event.start_at.isoformat(),
                    event.end_at.isoformat() if event.end_at else "",
                    "true" if event.all_day else "false",
                    event.location or "",
                    event.recurrence_rule or "",
                    event.recurrence_end_at.isoformat() if event.recurrence_end_at else "",
                    event.color or "",
                    "true" if event.cancelled else "false",
                    event.cancellation_reason or "",
                    ";".join(str(m) for m in reminders.get(event.id, [])),
                    usernames.get(event.created_by, ""),
                ]
            )
    print(f"Exported {len(events)} calendar event(s) to {file_path}.")


async def import_period(
    *, file_path: Path, username: str, dry_run: bool, delete_missing: bool, skip_confirm: bool
) -> None:
    if not file_path.exists():
        print(f"No such file: {file_path}")
        return

    parsed, errors = _parse_period_rows(file_path)
    if errors:
        for error in errors:
            print(error)
        print(f"{len(errors)} row(s) failed validation — nothing imported.")
        return

    async with async_session_factory() as db:
        user = await user_repo.get_by_username(db, username)
        if user is None:
            print(f"No user named {username!r}.")
            return

        creates: list[PeriodCycleCreate] = []
        updates: list[tuple[PeriodCycle, PeriodCycleCreate]] = []
        for line_no, row_id, payload in parsed:
            if row_id is None:
                creates.append(payload)
                continue
            cycle = await period_repo.get_cycle(db, row_id)
            if cycle is None:
                errors.append(f"row {line_no}: id {row_id} not found")
            elif cycle.user_id != user.id:
                errors.append(f"row {line_no}: id {row_id} belongs to a different account")
            else:
                updates.append((cycle, payload))

        if errors:
            for error in errors:
                print(error)
            print(f"{len(errors)} row(s) failed validation — nothing imported.")
            return

        existing = await period_repo.list_cycles(db, user.id)
        kept_ids = {cycle.id for cycle, _ in updates}
        missing = [cycle for cycle in existing if cycle.id not in kept_ids]

        if dry_run:
            for payload in creates:
                print(f"  CREATE {payload.cycle_start_date}  flow={payload.flow_intensity}")
            for cycle, payload in updates:
                print(f"  UPDATE {cycle.id}  {payload.cycle_start_date}  flow={payload.flow_intensity}")
            if delete_missing:
                for cycle in missing:
                    print(f"  DELETE {cycle.id}  {cycle.cycle_start_date}")
            elif missing:
                print(f"{len(missing)} existing row(s) not present in the file (would be left untouched).")
            print(
                f"Dry run: {len(creates)} to create, {len(updates)} to update, "
                f"{len(missing) if delete_missing else 0} to delete. No changes made."
            )
            return

        if missing:
            if delete_missing:
                if not skip_confirm:
                    print(f"The following {len(missing)} row(s) are not present in the file and will be DELETED:")
                    for cycle in missing:
                        print(f"  {cycle.id}  {cycle.cycle_start_date}")
                    answer = input("Type DELETE to continue: ")
                    if answer != "DELETE":
                        print("Aborted — no changes made.")
                        return
            else:
                print(
                    f"{len(missing)} existing row(s) not present in the file — left untouched "
                    "(pass --delete-missing to remove them)."
                )

        for payload in creates:
            await period_repo.create_cycle(db, user_id=user.id, **payload.model_dump())
        for cycle, payload in updates:
            for field, value in payload.model_dump().items():
                setattr(cycle, field, value)
        if delete_missing:
            for cycle in missing:
                await period_repo.delete_cycle(db, cycle)

        await db.commit()
        deleted_count = len(missing) if delete_missing else 0
        print(f"Imported for {username!r}: {len(creates)} created, {len(updates)} updated, {deleted_count} deleted.")


async def import_calendar(
    *, file_path: Path, username: str, dry_run: bool, delete_missing: bool, skip_confirm: bool
) -> None:
    if not file_path.exists():
        print(f"No such file: {file_path}")
        return

    parsed, errors = _parse_calendar_rows(file_path)
    if errors:
        for error in errors:
            print(error)
        print(f"{len(errors)} row(s) failed validation — nothing imported.")
        return

    async with async_session_factory() as db:
        user = await user_repo.get_by_username(db, username)
        if user is None:
            print(f"No user named {username!r}.")
            return

        creates: list[CalendarEventCreate] = []
        updates: list[tuple[CalendarEvent, CalendarEventCreate]] = []
        for line_no, row_id, payload in parsed:
            if row_id is None:
                creates.append(payload)
                continue
            event = await calendar_repo.get_by_id(db, row_id)
            if event is None:
                errors.append(f"row {line_no}: id {row_id} not found")
            else:
                updates.append((event, payload))

        if errors:
            for error in errors:
                print(error)
            print(f"{len(errors)} row(s) failed validation — nothing imported.")
            return

        existing = await calendar_repo.list_all(db)
        kept_ids = {event.id for event, _ in updates}
        missing = [event for event in existing if event.id not in kept_ids]

        if dry_run:
            for payload in creates:
                print(f"  CREATE {payload.start_at}  {payload.type.value}: {payload.title}")
            for event, payload in updates:
                print(f"  UPDATE {event.id}  {payload.start_at}  {payload.type.value}: {payload.title}")
            if delete_missing:
                for event in missing:
                    print(f"  DELETE {event.id}  {event.start_at}  {event.type.value}: {event.title}")
            elif missing:
                print(f"{len(missing)} existing row(s) not present in the file (would be left untouched).")
            print(
                f"Dry run: {len(creates)} to create, {len(updates)} to update, "
                f"{len(missing) if delete_missing else 0} to delete. No changes made."
            )
            return

        if missing:
            if delete_missing:
                if not skip_confirm:
                    print(f"The following {len(missing)} row(s) are not present in the file and will be DELETED:")
                    for event in missing:
                        print(f"  {event.id}  {event.start_at}  {event.type.value}: {event.title}")
                    answer = input("Type DELETE to continue: ")
                    if answer != "DELETE":
                        print("Aborted — no changes made.")
                        return
            else:
                print(
                    f"{len(missing)} existing row(s) not present in the file — left untouched "
                    "(pass --delete-missing to remove them)."
                )

        for payload in creates:
            event = await calendar_repo.create(
                db,
                created_by=user.id,
                **{field: getattr(payload, field) for field in _CALENDAR_EVENT_FIELDS},
            )
            await calendar_repo.set_reminders(db, event.id, payload.reminder_minutes_before)
        for event, payload in updates:
            for field in _CALENDAR_EVENT_FIELDS:
                setattr(event, field, getattr(payload, field))
            await calendar_repo.set_reminders(db, event.id, payload.reminder_minutes_before)
        if delete_missing:
            for event in missing:
                await calendar_repo.soft_delete(db, event)

        await db.commit()
        deleted_count = len(missing) if delete_missing else 0
        print(
            f"Imported: {len(creates)} created (attributed to {username!r}), "
            f"{len(updates)} updated, {deleted_count} deleted."
        )


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser(
        "reset-all", help="Permanently delete all data and sign both accounts out"
    )
    reset_parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt")

    reset_password_parser = subparsers.add_parser(
        "reset-password", help="Generate a one-time password for a forgotten account password"
    )
    reset_password_parser.add_argument("--user", required=True, help="Username whose password to reset")

    subparsers.add_parser("register", help="Interactively register a new account")

    test_notification_parser = subparsers.add_parser(
        "test-notification", help="Send a real push to a user's registered devices, to verify delivery"
    )
    test_notification_parser.add_argument("--user", required=True, help="Username whose devices to push to")

    list_devices_parser = subparsers.add_parser(
        "list-devices", help="List a user's registered FCM tokens (platform, app version, last active)"
    )
    list_devices_parser.add_argument("--user", required=True, help="Username whose devices to list")
    list_devices_parser.add_argument(
        "--active-days",
        type=int,
        default=DEFAULT_ACTIVE_WITHIN_DAYS,
        help=f"Days since last check-in to count as active (default: {DEFAULT_ACTIVE_WITHIN_DAYS})",
    )
    list_devices_parser.add_argument(
        "--count-only",
        action="store_true",
        help="Print just the active-device count (honors --active-days), no per-device listing",
    )

    export_period_parser = subparsers.add_parser(
        "export-period", help="Export one account's period cycles to a CSV file"
    )
    export_period_parser.add_argument("--file", type=Path, required=True, help="Path to write the CSV file")
    export_period_parser.add_argument("--user", required=True, help="Username whose cycles to export")

    export_calendar_parser = subparsers.add_parser(
        "export-calendar", help="Export the entire shared calendar to a CSV file"
    )
    export_calendar_parser.add_argument("--file", type=Path, required=True, help="Path to write the CSV file")

    import_period_parser = subparsers.add_parser(
        "import-period",
        help="Create/update/delete period cycles for one account from a CSV file (id column drives create vs. update)",
    )
    import_period_parser.add_argument("--file", type=Path, required=True, help="Path to the CSV file")
    import_period_parser.add_argument("--user", required=True, help="Username the rows belong to")
    import_period_parser.add_argument(
        "--dry-run", action="store_true", help="Preview the create/update/delete plan only — write nothing"
    )
    import_period_parser.add_argument(
        "--delete-missing",
        action="store_true",
        help="Delete existing rows for this account whose id is absent from the file",
    )
    import_period_parser.add_argument("--yes", action="store_true", help="Skip the delete confirmation prompt")

    import_calendar_parser = subparsers.add_parser(
        "import-calendar",
        help="Create/update/delete calendar events from a CSV file (id column drives create vs. update)",
    )
    import_calendar_parser.add_argument("--file", type=Path, required=True, help="Path to the CSV file")
    import_calendar_parser.add_argument("--user", required=True, help="Username newly created rows are attributed to")
    import_calendar_parser.add_argument(
        "--dry-run", action="store_true", help="Preview the create/update/delete plan only — write nothing"
    )
    import_calendar_parser.add_argument(
        "--delete-missing",
        action="store_true",
        help="Delete existing calendar events whose id is absent from the file",
    )
    import_calendar_parser.add_argument("--yes", action="store_true", help="Skip the delete confirmation prompt")

    args = parser.parse_args()

    if args.command == "reset-all":
        asyncio.run(reset_all(skip_confirm=args.yes))
    elif args.command == "reset-password":
        asyncio.run(reset_password(username=args.user))
    elif args.command == "register":
        asyncio.run(register())
    elif args.command == "test-notification":
        asyncio.run(test_notification(username=args.user))
    elif args.command == "list-devices":
        asyncio.run(list_devices(username=args.user, active_within_days=args.active_days, count_only=args.count_only))
    elif args.command == "export-period":
        asyncio.run(export_period(file_path=args.file, username=args.user))
    elif args.command == "export-calendar":
        asyncio.run(export_calendar(file_path=args.file))
    elif args.command == "import-period":
        asyncio.run(
            import_period(
                file_path=args.file,
                username=args.user,
                dry_run=args.dry_run,
                delete_missing=args.delete_missing,
                skip_confirm=args.yes,
            )
        )
    elif args.command == "import-calendar":
        asyncio.run(
            import_calendar(
                file_path=args.file,
                username=args.user,
                dry_run=args.dry_run,
                delete_missing=args.delete_missing,
                skip_confirm=args.yes,
            )
        )


if __name__ == "__main__":
    main()
