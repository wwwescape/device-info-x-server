# Administration

Day-to-day admin tasks for Device Info X Server, mostly through the `app.cli` commands. Back to the [README](../README.md).

## Contents

1. [Pairing your two accounts](#pairing-your-two-accounts)
2. [Registering an account for your partner](#registering-an-account-for-your-partner)
3. [Setting up Period Tracker for your partner](#setting-up-period-tracker-for-your-partner)
4. [Resetting all data](#resetting-all-data)
5. [Resetting a forgotten password](#resetting-a-forgotten-password)
6. [Enabling and disabling guided tours](#enabling-and-disabling-guided-tours)
7. [Enabling and disabling What's New announcements](#enabling-and-disabling-whats-new-announcements)
8. [Managing DIX AI Insights](#managing-dix-ai-insights)
9. [Recording the latest app build (in-app update check)](#recording-the-latest-app-build-in-app-update-check)
10. [Testing push notifications](#testing-push-notifications)
11. [Debugging message delivery](#debugging-message-delivery)
12. [CSV data import](#csv-data-import)

---

## Pairing your two accounts

1. **Register both accounts.** Each partner installs the Android app,
   points it at your server's URL, and registers using the shared
   `SERVER_SETUP_TOKEN` from your `.env`. The server permanently refuses
   registration once 2 accounts exist, regardless of the token — so do this
   before losing/rotating the token.
2. **Generate a pairing code.** From one account: `POST
   /api/v1/pairing/code` returns a code and a 15-minute expiry. The Android
   app surfaces this in its UI.
3. **Share the code out-of-band** — read it out loud, text it, whatever.
   It's high-entropy and single-use, but it's not a secret worth
   encrypting in transit separately.
4. **Pair from the other account:** `POST /api/v1/pairing/pair {"code":
   "..."}`. Both accounts are now linked — messaging, the shared calendar,
   special events, and the Safe Locker all become available.
5. To unpair (e.g. to re-pair with a fresh setup), either partner can call
   `DELETE /api/v1/pairing` — prior data is retained but those features are
   locked until re-paired.

---

## Registering an account for your partner

If your partner isn't comfortable filling in the registration screen
themselves (or a registration attempt keeps failing and you can't see why),
whoever has `docker exec` access can create the account for them directly:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli register
```

This walks through each field one at a time — username, name, gender,
birthday, then password (typed twice, hidden) — and reprompts just that
field with a plain-English reason if something's invalid, instead of the
generic `422` the HTTP endpoint returns. It reads `SERVER_SETUP_TOKEN` from
the server's own config, so there's nothing to look up or paste, and it asks
for a final confirmation before writing anything. Registration is still
hard-capped at 2 accounts either way.

---

## Setting up Period Tracker for your partner

Same "operator does it for them" shape as registration above — useful if
your partner wants Period Tracker pre-seeded with their last period before
they've opened the app themselves, or a registration was done on their
behalf and they'd rather not do first-time setup manually:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli setup-period --user alice
```

It prompts for the last period's start date (`YYYY-MM-DD`, can't be in the
future) and its length in days (3–7, defaults to 5 if left blank), shows
what it's about to log, and asks you to type `YES` to confirm before writing
anything. Period Tracker logs one row per day, not per whole period (see
[CSV data import](#csv-data-import) below) — this creates one row per day in
that range, each with Medium flow intensity, individually editable from the
app afterward the same as any other logged day.

If the account already has logged days, it says so and asks whether to log
another period anyway rather than silently adding to existing history.

One thing this can't replicate: the Android app's own onboarding also seeds
two on-device-only prediction estimates (an assumed cycle length and period
length) that make the very first prediction more accurate before a second
real cycle exists to average real gaps from — those live in the app's local
storage only and are never synced to the server, so a CLI-created setup
falls back to a textbook 28-day average for that first prediction instead.
It self-corrects the moment a second cycle is logged.

---

## Resetting all data

For a full wipe — starting over after testing, or handing the server to a
new pair of accounts — a maintenance command ships inside the `api` image,
run via `docker exec`:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli reset-all
```

This permanently deletes **everything**: both user accounts, pairing state,
messages, calendar events, special events, period tracking, Safe Locker
contents, and all uploaded media files. It also signs both accounts out
immediately — `GET`/`POST` requests with an existing access token start
failing right away rather than waiting for the token's natural expiry,
since every request re-checks the user still exists in the database.

- Requires `-it` — it prompts you to type `RESET` to confirm before
  touching anything. Pass `--yes` instead to skip the prompt for scripted/
  non-interactive use.
- There's no undo. If you might want the data back, run
  `./scripts/backup_db.sh` first — see [Backups and restore](deployment.md#backups-and-restore).
- Registration is hard-capped at 2 accounts (see
  [Environment variables](deployment.md#environment-variables)), so after a reset both
  partners need to re-register with `SERVER_SETUP_TOKEN`, same as first-time
  setup.

---

## Resetting a forgotten password

There's no self-service "forgot password" flow — no email/SMS provider is
wired up anywhere in this server, and building one for a 2-account app one
couple hosts for themselves isn't worth the added attack surface. Instead,
whoever has `docker exec` access (already the trusted operator for a private
deployment like this one) can generate a one-time password:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli reset-password --user alice
```

This prints a new, randomly-generated one-time password to the terminal —
**share it with the account owner directly** (call, text, in person); it's
never written anywhere else, and the command doesn't send it anywhere on its
own. Behind the scenes:

- The account's password is replaced with the OTP, and the account is
  flagged so the app **forces a real password to be set** the moment
  someone logs in with it — the OTP itself only ever works once.
- **Every existing session for that account is signed out** (all devices),
  since a forgotten/compromised password means any session predating the
  reset should no longer be trusted.
- The other partner's account and data are untouched.

If the affected partner is mid-login when this runs, nothing breaks — they
just log in with the OTP like a normal password and are prompted to set a
new one before the console unlocks.

---

## Enabling and disabling guided tours

The Android client shows a one-time coach mark ("guided tour") the first
time someone encounters certain features — e.g. the Messages screen's "I'm
Online" icon. Once dismissed, a given tour never shows again for that
account, even across an uninstall/reinstall, since the "seen" state lives
server-side rather than in local app storage.

To make a dismissed tour show again — useful after changing a tour's
wording or target during development, or if a user asks to see one again —
use `enable-tours`:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli enable-tours --user alice
```

Run with just `--user`, it lists every tour that account has dismissed and
prompts interactively — type a specific tour key to enable just that one,
`ALL` to enable every tour for that account, or anything else to abort.
Pass `--tour` to enable one specific tour non-interactively instead,
without the prompt:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli enable-tours --user alice --tour online_ping
```

To suppress a tour from showing — including pre-emptively, before the
account has ever reached it (e.g. a tour that's broken or not ready yet) —
use `disable-tours`, which works the same way:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli disable-tours --user alice
```

Run with just `--user`, it lists every tour that account has dismissed and
prompts interactively — type a specific tour key to disable just that one,
`ALL` to disable every tour listed, or anything else to abort. Pass
`--tour` to disable one specific tour non-interactively instead,
without the prompt:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli disable-tours --user alice --tour online_ping
```

Unlike `enable-tours --tour`, the key doesn't need to already be dismissed, since
suppressing a tour the account hasn't seen yet is the main use case

Both commands only affect one account and, unless `ALL` is used, one tour —
the other partner's tour state, and everything else about the account, is
untouched.

Available tours, for reference (grows as new ones are added on the client —
see `FeatureTourTarget` call sites under `console/ui/` in the Android app):

| `tour_key`             | Where it shows                                                    |
| ---------------------- | ------------------------------------------------------------------ |
| `online_ping`          | Messages screen, the "I'm Online" header icon                      |
| `alert_style`          | Settings → Notifications, the "Alert style" (High/Default) group   |
| `sound_mode`           | Settings → Notifications, the "Sound" (Always/Limit/Muted) group   |
| `notification_sounds`  | Settings → Notifications, the "Notification sounds" (tone) group   |

---

## Enabling and disabling What's New announcements

The Android client shows a scrollable popup — a firework-themed take on the guided-tour idea —
listing crisp bullet points for newly shipped features worth calling out. It's shown once per
account, the next time they open the console after a bullet exists, using the same server-side
"seen" state shape as guided tours (not local app storage). Unlike a guided tour, the announcement
*text* itself lives entirely in the client app — this server only ever tracks which announcement
tags a given account has already been shown, never the copy.

To make an already-dismissed announcement show again — useful after fixing a typo in its wording,
or if a user asks to see one again — use `enable-whats-new`:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli enable-whats-new --user alice
```

Run with just `--user`, it lists every announcement that account has dismissed and prompts
interactively — type a specific tag to enable just that one, `ALL` to enable every announcement
for that account, or anything else to abort. Pass `--tag` to enable one specific announcement
non-interactively instead, without the prompt:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli enable-whats-new --user alice --tag duress_code_2026_08
```

To suppress an announcement from showing — including pre-emptively, before the account has ever
reached it (e.g. one with a typo, or not ready yet) — use `disable-whats-new`, which works the
same way:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli disable-whats-new --user alice
```

Run with just `--user`, it lists every announcement that account has dismissed and prompts
interactively — type a specific tag to disable just that one, `ALL` to disable every announcement
listed, or anything else to abort. Pass `--tag` to disable one specific announcement
non-interactively instead, without the prompt:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli disable-whats-new --user alice --tag duress_code_2026_08
```

Unlike `enable-whats-new --tag`, the tag doesn't need to already be dismissed, since suppressing
an announcement the account hasn't seen yet is the main use case.

Both commands only affect one account and, unless `ALL` is used, one announcement — the other
partner's announcement state, and everything else about the account, is untouched.

Available tags, for reference (grows as new announcements are added on the client — see
`WHATS_NEW_ENTRIES` in `console/data/whatsnew/WhatsNewEntries.kt` in the Android app):

| `tag`                     | What it announces      |
| ------------------------- | ----------------------- |
| `game_room_2026_08`       | Tic Tac Toe game room   |
| `duress_code_2026_08`     | Duress Code             |
| `scheduled_send_2026_08`  | Scheduled Send          |
| `notepad_2026_08`         | Notepad                 |
| `calling_2026_08`         | Voice/video calling     |
| `gif_picker_2026_09`      | GIF tab in the emoji picker |
| `reactions_2026_09`       | Reactions tab in the emoji picker |

---

## Managing DIX AI Insights

The Android client shows a lightbulb-themed popup — mechanically similar to the What's New
announcement above, using the same server-side "seen" state shape — surfacing short "DIX AI
Insight" one-liners. Unlike What's New and guided tours, DIX AI isn't real AI yet and has no
client-shipped content at all: every insight's *text* is authored here, on the server, through
this CLI, and whoever runs these commands is responsible for its accuracy.

To add a new insight, use `add-insight`:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli add-insight --text "You two have talked every day this week!"
```

Global by default — shown to both accounts, like a What's New announcement. Pass `--user` to
scope it to that one account instead — a server only ever has the 2 accounts, so "targeted" simply
means the other account never sees it:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli add-insight --text "..." --user alice
```

`--text` accepts a constrained Markdown subset — rendered formatted in the popup rather than shown
as raw asterisks — following [markdownguide.org/basic-syntax](https://www.markdownguide.org/basic-syntax/)'s
own rules for each of these sections:

| Syntax | Example | Renders as |
| --- | --- | --- |
| Bold | `**bold text**` or `__bold text__` | **bold text** |
| Italic | `*italicized text*` or `_italicized text_` | *italicized text* |
| Bold and italic | `***bold and italic text***` | ***bold and italic text*** |
| Link | `[title](https://example.com)` | a tappable link reading "title" |
| URL/email autolink | `<https://example.com>` / `<name@example.com>` | a tappable link (email opens via `mailto:`) |
| Escaped character | `\*not italic\*` | \*not italic\* |

A link's optional `[title](url "Title Text")` form is accepted, but the title itself is discarded
— there's no touch-UI equivalent of a hover tooltip to show it. Only the strict `<...>`
angle-bracket form autolinks; a bare URL or email with no brackets around it renders as plain text.

`add-insight` validates this syntax before creating anything: an unbalanced `**`, an unclosed
`[title](`, or a malformed `<...>` is rejected outright with a syntax error and a pointer to
[markdownlivepreview.dev's validator](https://markdownlivepreview.dev/tools/markdown-validator) to
check it externally — nothing malformed ever reaches the popup.

This prints the new insight's id, which every other command below needs. To look it up again
later, use `list-insights`:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli list-insights
```

Lists every insight, oldest first, with its id, enabled state, target (`global` or
`user:<username>`), how many accounts have already dismissed it, and a text preview. Pass
`--enabled-only` to hide disabled insights.

To permanently remove an insight — cascading its seen-state for every account, with no undo — use
`delete-insight`:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli delete-insight --id <insight-id>
```

If you just want to pull an insight out of rotation without losing it (e.g. one with a typo), use
`disable-insight` instead, and `enable-insight` to bring it back:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli disable-insight --id <insight-id>
docker exec -it deviceinfoxserver_api python -m app.cli enable-insight --id <insight-id>
```

These are a content-level switch, not a per-account one — they control whether the insight is
offered to anyone who hasn't seen it yet at all. They never touch any account's existing dismissed
state: an account that already saw the insight before it was disabled still won't see it again
once it's re-enabled.

To let a dismissed insight show again for an account (or every account that had dismissed it —
useful after fixing a typo), use `reset-insight-seen`:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli reset-insight-seen --id <insight-id> --user alice
```

Pass `--user` to reset just that one account; omit it to reset every account that had already
dismissed it.

---

## Recording the latest app build (in-app update check)

Since this app is sideloaded rather than distributed through the Play Store,
there's no store-driven update mechanism — a partner running an older build
has no way to know a newer one exists unless told out of band. The server
closes that gap with one piece of state: the timestamp of the most recently
published build, which every paired client compares itself against
(`GET /releases/latest`) each time it connects.

The Android client identifies its own build with a hand-set
`BuildConfig.BUILD_TIMESTAMP` string (e.g. `2026-08-15-2144`), not the
manifest's real `versionCode` — this deliberately sidesteps Android's
install-downgrade protection, so it can be freely reset without any install
friction. Right after cutting and publishing a new build, record its
timestamp with `set-latest-build`:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli set-latest-build --timestamp 2026-08-15-2144
```

The value must match `BuildConfig.BUILD_TIMESTAMP` exactly (`app/build.gradle.kts`
in the Android repo) — comparison is a plain string inequality, not a date
parse. There's only ever one "latest" value, shared by both accounts.

Once a connected client's own `BUILD_TIMESTAMP` differs from what's recorded
here, it shows a small badge on the Settings gear icon and a dismissible
update card at the top of Settings, with a Download button that opens
`APK_DOWNLOAD_URL` (see [Environment variables](deployment.md#environment-variables)) in
the browser — there's no in-app installer, since this app deliberately
avoids requesting install-package permissions. Point `APK_DOWNLOAD_URL` at
wherever you host your own builds (e.g. a GitHub release asset); leave it
blank to disable the update card entirely, since a null download link means
there'd be nowhere useful for the button to send anyone.

---

## Testing push notifications

To check whether push is reaching a device — without touching any Messages,
Calendar, or Period Tracker data — send a one-off test push straight to that
account's registered devices:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli test-notification --user alice
```

This only reads that account's device tokens (the `devices` table); it
writes nothing anywhere. Unlike the app's real notifications — which are
always data-only, so the Android app decides how (and whether, in discreet
mode) to render them — this one includes a visible title and body, so the OS
displays it immediately regardless of the app's own notification logic. That
makes it a good check that Firebase delivery itself works end-to-end, but
it doesn't confirm the app's data-only notification handling is healthy —
that's still worth checking separately (e.g. by sending a real message).

A row in the `devices` table is keyed by *FCM token*, not by physical
device, and Firebase issues a new token on every reinstall/rebuild (common
during active development) or cleared app data — the old token dies the
moment the new one takes over, but is never deleted on its own. A token's
*age* doesn't tell you whether it's still valid; only actually trying to
deliver to it does. So `test-notification` sends to every registered token,
and prunes whichever ones Firebase itself reports back as permanently dead
(`UnregisteredError`) — the same cleanup the app's real notification path
already does for genuine messages. That's still a read/write against the
`devices` table only; Messages, Calendar, and Period Tracker data are never
touched.

The command prints how many of the account's devices it reached:

- `Sent to 1/1 device(s).` — delivered, and every registered token is live.
- ```
  Sent to 1/1 device(s).

  Additionally, removed 3 dead token(s) (superseded/uninstalled).
  ```
  — delivered to the current device; the `1/1` already excludes the 3 dead
  tokens from past installs/rebuilds, which were confirmed dead by Firebase
  and deleted, so they won't show up in `list-devices` (below) anymore.
- `No registered devices (FCM tokens) for this user.` — the partner hasn't
  logged in on a device yet, or notification permission was never granted.
- `Firebase Admin SDK not initialized (FIREBASE_SERVICE_ACCOUNT_JSON not
  set).` — see [Firebase setup](deployment.md#firebase-setup).

### Inspecting registered devices

To see what's actually registered — token suffix, platform, app version, and
when each was last active — for a given account:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli list-devices --user alice
```

The most recently active row is almost always the current device; older
rows are typically dead tokens from past installs/rebuilds — run
`test-notification` (above) to confirm and prune them, since `list-devices`
itself is read-only and won't delete anything.

`--count-only` prints just a count instead of the full listing, filtered to
rows whose `last_active_at` falls within `--active-days` (30 by default):

```bash
docker exec -it deviceinfoxserver_api python -m app.cli list-devices --user alice --count-only --active-days 7
```

Treat that count as a rough recency filter, not a validity check — a token
registered minutes ago by a fresh reinstall is just as likely to already be
dead as one from last month (see above for why age doesn't tell you
anything). For an authoritative live-device count, use `test-notification`.

---

## Debugging message delivery

If a partner got a push notification but the message itself never showed up
in the app, the fastest way to narrow down where it broke is to check
whether the message actually made it into the database — bypassing the API
and WebSocket layer entirely:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli list-messages
```

This prints the most recent messages from **both** accounts, newest on top,
in an ASCII table of timestamp, sender, and message body:

```
+---------------------+--------+----------------------------+
| Timestamp           | Sender | Message                    |
+---------------------+--------+----------------------------+
| 2026-08-22 03:41:12 UTC | alice  | hey are you around?    |
| 2026-08-22 03:40:58 UTC | bob    | <image>                 |
+---------------------+--------+----------------------------+
```

Non-text messages (image, voice, video, document, poll) show as `<type>`
rather than a body, since `body` is normally empty for them. If the message
you're chasing shows up here, it made it to the server fine and the bug is
client-side (sync, rendering, or push-to-fetch handling); if it's missing
entirely, the send never landed server-side despite the notification, and
the bug is upstream of the database write.

`--count` limits how many rows are shown (default 10); `--user` filters to
one account's sent messages instead of both:

```bash
docker exec -it deviceinfoxserver_api python -m app.cli list-messages --count 25
docker exec -it deviceinfoxserver_api python -m app.cli list-messages --user alice --count 5
```

This command is read-only — it never writes, deletes, or marks anything as
read.

---

## CSV data import

For backfilling historical calendar events or period day logs in bulk (e.g.
migrating from another app), or bulk-editing existing data without tapping
through the Android app one row at a time, four maintenance commands ship
inside the `api` image, same as `reset-all` above — out-of-band, run via
`docker exec`, no HTTP endpoint: `export-period`, `export-calendar`,
`import-period`, `import-calendar`.

The import commands validate **every row before writing anything** — if any
row fails validation, nothing is imported and every failing row is printed
with its line number, so you can fix the file and re-run instead of ending up
with a half-imported file. Neither import command sends a realtime
notification to the paired partner (unlike the equivalent app actions) — a
bulk import isn't "new" activity worth pushing a notification for.

Example files matching the column layouts below live in
[`samples/period_day_logs_example.csv`](../samples/period_day_logs_example.csv) and
[`samples/calendar_events_example.csv`](../samples/calendar_events_example.csv).

### Getting the CSV onto the server

`docker-compose.yml` bind-mounts `./imports` into the `api` container at
`/data/imports` (read/write, so exporting and reimporting can share the same
folder). Create it once:

```bash
mkdir -p imports
cp samples/calendar_events_example.csv imports/calendar_events.csv
cp samples/period_day_logs_example.csv imports/period_day_logs.csv
```

If you're running an existing deployment, pull the updated
`docker-compose.yml` and recreate the `api` container first — see
[Updating containers](deployment.md#updating-containers).

### Exporting existing data

```bash
docker exec -it deviceinfoxserver_api python -m app.cli export-period \
  --file /data/imports/period_day_logs.csv --user alice

docker exec -it deviceinfoxserver_api python -m app.cli export-calendar \
  --file /data/imports/calendar_events.csv
```

`export-period` is per-account (period tracking is private, matching the
app's own access rules). `export-calendar` always dumps the *entire* shared
calendar — there's no per-account or date-range filter, since the calendar
itself has no per-item ownership (see [Architecture](development.md#architecture)).

The exported file is meant to be edited and fed straight back into the
matching `import-*` command — add rows, change values, or delete rows — see
the `id` column below for how re-importing reconciles those edits.

### Importing period day logs

```bash
docker exec -it deviceinfoxserver_api python -m app.cli import-period \
  --file /data/imports/period_day_logs.csv --user alice
```

Period Tracker logs one row per day, not per whole period — a day only
counts toward cycle prediction once `flow_intensity` is set to `light`,
`medium`, or `heavy`; a row with only `symptoms`/`notes` (e.g. spotting, or a
symptom on a day that isn't part of a period at all) doesn't.

| Column | Required | Format | Notes |
|---|---|---|---|
| `id` | No | UUID | Blank ⇒ create a new row. A value matching an existing row's `id` ⇒ update that row instead (see "Updating and deleting" below). |
| `log_date` | Yes | `YYYY-MM-DD` | |
| `symptoms` | No | `;`-separated list, e.g. `cramps;fatigue` | |
| `flow_intensity` | No | `light`, `medium`, or `heavy` | |
| `notes` | No | free text | |

### Importing calendar events

```bash
docker exec -it deviceinfoxserver_api python -m app.cli import-calendar \
  --file /data/imports/calendar_events.csv --user alice
```

| Column | Required | Format | Notes |
|---|---|---|---|
| `id` | No | UUID | Blank ⇒ create a new row. A value matching an existing row's `id` ⇒ update that row instead (see "Updating and deleting" below). |
| `type` | Yes | one of `birthday`, `wedding_anniversary`, `anniversary`, `vacation`, `planned_trip`, `planned_date`, `unplanned_date`, `planned_drive`, `unplanned_drive`, `reminder`, `custom` | |
| `title` | Yes | 1–255 chars | |
| `description` | No | free text | |
| `start_at` | Yes | ISO 8601 datetime, e.g. `2026-05-14T00:00:00Z` | Include a `Z`/offset — a bare, timezone-less timestamp is ambiguous. |
| `end_at` | No | ISO 8601 datetime | |
| `all_day` | No | `true`/`false` | Defaults to `false`. |
| `location` | No | up to 255 chars | |
| `recurrence_rule` | No | RFC5545 RRULE, e.g. `FREQ=YEARLY` | Only valid on `birthday`, `wedding_anniversary`, `anniversary`, `reminder`, or `custom` rows — same restriction the app enforces. |
| `recurrence_end_at` | No | ISO 8601 datetime | |
| `color` | No | hex, e.g. `#FF5A8A` | |
| `cancelled` | No | `true`/`false` | Defaults to `false`. Only valid on `planned_date`, `planned_drive`, `planned_trip`, or `custom` rows — same restriction the app enforces. |
| `cancellation_reason` | No | free text | Requires `cancelled` to be `true` on the same row. |
| `cancelled_by` | No | `both`, or a username | Requires `cancelled` to be `true` on the same row. A username must belong to one of the two paired accounts — exported the same way (a username, not a raw id), so a round-tripped file always works. |
| `reminder_minutes_before` | No | `;`-separated integers, e.g. `1440;60` | |
| `created_by` | No | username | Export-only — shows who originally created the event. Ignored on import; you can't reassign an existing event's creator through the CSV. |

`--user` must be the username of one of the two registered accounts. For
period day logs it's whose data every row belongs to. For calendar events
(shared, no per-row owner) it only matters for brand-new rows (blank `id`) —
it's who they get attributed to; edits to existing rows never change who
created them.

### Updating and deleting via re-import

Because each row's `id` is the reconciliation key, editing an exported file
and reimporting it is a full add/update/delete round-trip, not just an
append:

- A row with **no `id`** creates a new record.
- A row whose **`id` matches an existing record** replaces that record
  entirely — every column in the row overwrites the corresponding field,
  **including blanking a cell to clear it** (there's no "leave unchanged"
  concept in a CSV row; if you don't want a field to change, copy its current
  value through unedited). An `id` that doesn't exist, or a period `id`
  belonging to the *other* account, aborts the whole import as a validation
  error, same as a malformed date or an out-of-range value.
- An **existing record whose `id` isn't anywhere in the file** is left alone
  by default — the import just prints how many rows were skipped this way.
  Pass `--delete-missing` to actually delete them instead. Since that
  compares against **everything** currently in scope — every day that
  account has ever logged, or the *entire* shared calendar — only use it on
  a file that came from a full, unedited-down export. Trimming the file to a
  subset of rows before reimporting with `--delete-missing` will delete
  everything you left out.
- When `--delete-missing` would actually delete something, the command
  prints every row about to go and asks you to type `DELETE` to continue —
  declining aborts the entire run, nothing is written. Pass `--yes` to skip
  the prompt for scripted use.

```bash
# Preview only — safe to run any time, never writes:
docker exec -it deviceinfoxserver_api python -m app.cli import-period \
  --file /data/imports/period_day_logs.csv --user alice --dry-run

# Add/update rows, and remove anything no longer in the file:
docker exec -it deviceinfoxserver_api python -m app.cli import-period \
  --file /data/imports/period_day_logs.csv --user alice --delete-missing
```

`--dry-run` works the same on both commands and previews the full plan
(how many rows would be created, updated, and — if `--delete-missing` is
also passed — deleted) without touching the database or prompting for
confirmation.
