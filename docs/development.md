# Development

Architecture, local development, migrations, and API docs for Device Info X Server. Back to the [README](../README.md).

## Contents

1. [Architecture](#architecture)
2. [Tech stack](#tech-stack)
3. [Repository layout](#repository-layout)
4. [Media type policy](#media-type-policy)
5. [Local development](#local-development)
6. [Database migrations](#database-migrations)
7. [API documentation](#api-documentation)

---

## Architecture

```
Nginx (TLS, reverse proxy, protected static media via X-Accel-Redirect)
   │
   ▼
FastAPI app (single process — see the note in docker/entrypoint.sh)
  api/         → HTTP routers
  ws/          → WebSocket connection manager + realtime protocol
  services/    → business logic
  repositories/→ SQLAlchemy queries
  models/      → SQLAlchemy ORM models
  core/        → config, security, dependencies
  integrations/→ Firebase Admin (FCM)
  storage/     → local filesystem media storage
  tasks/       → APScheduler reminder sweep
   │
   ▼
PostgreSQL
```

Every deployment of this backend serves **exactly one couple** (2 user
accounts, hard-capped — see [Environment variables](deployment.md#environment-variables)).
There's no multi-tenant conversation model: messages, calendar events, and
special events are simply shared between whichever two accounts exist.
Period tracking and the Safe Locker are more private — see the source for
exact per-feature access rules.

Full deployment picture:

```
                              Internet
                                 │
                    (DNS hostname → server's public IP)
                                 │
                     Router/firewall: port-forward
              443/tcp, 80/tcp, 3478/tcp+udp, 49160-49200/udp
                                 │
                    Docker host (VPS, home server…)
        ┌────────────────────────────────────────────────┐
        │                Docker network                  │
        │                                                │
        │   Nginx (TLS, reverse proxy) ──── coturn       │
        │        │         ▲                (TURN/STUN)  │
        │        ▼         │ X-Accel-Redirect            │
        │     FastAPI (api) ── media_data volume         │
        │        │                                       │
        │        ▼                                       │
        │   PostgreSQL (db, internal-only)               │
        └────────────────────────────────────────────────┘
                                 │
                         outbound HTTPS only
                                 ▼
                    Firebase Cloud Messaging (external)
```

`certbot` (Let's Encrypt) also runs alongside Nginx, not pictured above for
clarity — see [HTTPS, Let's Encrypt, and the reverse proxy](deployment.md#https-lets-encrypt-and-the-reverse-proxy).
"Router/firewall: port-forward" only applies if your host is behind NAT
without a public IP (typical for a home network). A VPS/cloud host with a
static public IP skips that step entirely and just opens the same ports in
its firewall/security group — see [Deploying with Docker](deployment.md#deploying-with-docker).

---

## Tech stack

Python 3.13 · FastAPI · PostgreSQL · SQLAlchemy 2.0 (async) · Alembic · JWT ·
Argon2 · WebSockets · Docker / Docker Compose · Nginx · Coturn · OpenAPI ·
Pydantic v2.

The only external service this backend talks to is **Firebase Cloud
Messaging** (outbound HTTPS only, for push notifications). Everything else —
database, media storage, TLS, TURN/STUN — is self-hosted.

Prebuilt multi-arch (`linux/amd64` + `linux/arm64`) images are published on
every tagged release: the api itself as
[`wwwescape/device-info-x-server`](https://hub.docker.com/r/wwwescape/device-info-x-server),
plus `wwwescape/device-info-x-server-nginx` and
`wwwescape/device-info-x-server-coturn` — thin wrappers around the stock
Nginx/coturn images with this repo's config baked in via `COPY` (see
`nginx/Dockerfile`, `coturn/Dockerfile`). That means a deploy using prebuilt
images needs only `docker-compose.yml` and `.env` on disk — no git clone,
no hand-copying `nginx.conf` or `turnserver.conf` onto the host. See
[Deploying with Docker](deployment.md#deploying-with-docker),
[Local development](#local-development), and
[Updating containers](deployment.md#updating-containers).

---

## Repository layout

```
device-info-x-server/
├── docker-compose.yml                    # db, api, nginx, certbot, coturn
├── docker-compose.override.yml.example   # local dev overrides (copy, don't edit in place)
├── Dockerfile                            # multi-stage build for the api image
├── .env.example                          # copy to .env and fill in
├── alembic/                              # database migrations
├── app/                                  # the FastAPI application (see Architecture)
├── nginx/                                # nginx.conf + the app.conf template + Dockerfile
├── coturn/                               # turnserver.conf + Dockerfile
├── secrets/                              # firebase-service-account.json.example (real file is git-ignored)
├── samples/                              # example CSVs for the CSV import commands
├── scripts/                              # backup/restore_db.sh, backup/restore_media.sh, init_letsencrypt.sh, renew_cert.sh
└── tests/                                # pytest suite
```

---

## Media type policy

What file types Messages, Calendar, and Safe Locker accept, and why — enforced server-side in
`app/services/media_service.py` (`_CATEGORY_RULES`, `_IMAGE_MIME_TYPES`, `_VIDEO_MIME_TYPES`).

### Supported kinds, by feature

| Kind | Messages | Calendar | Safe Locker |
|---|:---:|:---:|:---:|
| **PHOTO** | ✅ | ✅ | ✅ |
| **VIDEO** | ✅ | ✅ | ✅ |
| **DOCUMENT** | ✅ | ✅ | ✅ |
| **NOTE** | — | — | Schema-only (see below) |
| **OTHER** | — | — | Schema-only (see below) |

- **PHOTO** — a still image. Called `PHOTO` in Safe Locker (`LockerCategory.PHOTO`) and `IMAGE`
  in Messages/Calendar (`MessageType.IMAGE`, `MediaCategory.{MESSAGE,CALENDAR}_IMAGE`) — same
  kind, different name per feature.
- **VIDEO** — a video with a real-frame poster thumbnail, viewable in-app (Media3 playback),
  supported identically across all three features.
- **DOCUMENT** — any file, download-only (no in-app viewer, matching WhatsApp/Signal's document
  attachments) — see the mime-type table below for why this one stays intentionally unrestricted
  while PHOTO/VIDEO don't.
- **NOTE** / **OTHER** — exist only as `LockerCategory` enum values in the data model
  (`app/models/locker.py`), for forward-compatibility: a `LockerItem`'s `media_id` is optional at
  the schema level, so a `NOTE` (a title/description-only entry with no attached file) or `OTHER`
  (a catch-all outside photo/video/document) is something the API would accept and store today.
  But the Android client only ever *creates* PHOTO/VIDEO/DOCUMENT locker items — see
  `VaultRepository.importImages`/`importVideos`/`importDocuments` — and treats NOTE/OTHER as
  **read-only, round-trip support only**, in case some other client ever creates one; there's no
  UI path to create either in the app today. Messages and Calendar have no NOTE/OTHER concept at
  all: a plain-text message (`MessageType.TEXT`) is the closest thing to a "note," but it isn't a
  media attachment kind, and Calendar attachments only ever come as image/video/document.

**Images and videos are restricted to a curated allow-list.** Every image/video category — in
Messages, Calendar, and profile avatars — only accepts a small set of standard mime types. An
upload outside the list is rejected with a 4xx before it ever touches disk.

**Documents and Safe Locker files are intentionally unrestricted.** Any mime type is accepted.
This is deliberate, not an oversight: Safe Locker exists to hold arbitrary private files (a
scanned ID, a PDF, a zip, an APK backup — whatever the two of you need to stash), and a
"document" attachment in Messages/Calendar is meant to work the way WhatsApp/Signal's document
attachments do — send any file, no type gate. Locking that down would trade away the app's
actual use case for a marginal reduction in attack surface; the size cap is what bounds the risk
instead.

| Category | Mime types | Size cap (env var) |
|---|---|---|
| Message image | `image/jpeg`, `image/png`, `image/webp`, `image/gif` | `MAX_IMAGE_SIZE_MB` (15) |
| Message voice note | `audio/aac`, `audio/mp4`, `audio/m4a`, `audio/mpeg`, `audio/ogg`, `audio/wav`, `audio/webm`, `audio/3gpp` | `MAX_VOICE_SIZE_MB` (20) |
| Message video | `video/mp4`, `video/quicktime`, `video/webm`, `video/3gpp`, `video/x-matroska` | `MAX_VIDEO_SIZE_MB` (150) |
| Message document | *unrestricted* | `MAX_DOCUMENT_SIZE_MB` (50) |
| Calendar image | same as Message image | `MAX_IMAGE_SIZE_MB` (15) |
| Calendar video | same as Message video | `MAX_VIDEO_SIZE_MB` (150) |
| Calendar document | *unrestricted* | `MAX_DOCUMENT_SIZE_MB` (50) |
| Safe Locker file (photo/video/document) | *unrestricted* | `MAX_LOCKER_FILE_SIZE_MB` (50) |
| Profile avatar | same as Message image | `MAX_AVATAR_SIZE_MB` (5) |
| Message link preview thumbnail | same as Message image | hardcoded 5MB, not env-configurable |

A video's poster thumbnail must itself be an upload from that video category's paired image
category (a message video's thumbnail must be a `message_image` upload, a calendar video's a
`calendar_image` upload) — Safe Locker is the one exception, since it has a single category
covering every item kind, so a locker video's thumbnail must be another `locker_file` upload.

To add a mime type to an image/video allow-list, edit `_IMAGE_MIME_TYPES`/`_VIDEO_MIME_TYPES` in
`media_service.py` — every category that reuses that set picks up the change automatically. To
restrict documents/Locker instead of leaving them open, give `MESSAGE_DOCUMENT`/
`CALENDAR_DOCUMENT`/`LOCKER_FILE` their own mime sets in `_CATEGORY_RULES` in place of the
current `None`.

---

## Local development

You don't need Nginx or coturn for local iteration:

```bash
cp .env.example .env
cp docker-compose.override.yml.example docker-compose.override.yml
cp secrets/firebase-service-account.json.example secrets/firebase-service-account.json
# edit .env: set a real POSTGRES_PASSWORD, JWT_SECRET_KEY, SERVER_SETUP_TOKEN
docker compose up --build db api
```

The override file sets `ENABLE_DOCS=true` (Swagger UI at
`http://localhost:8000/docs`), `MEDIA_SERVE_MODE=direct` (no Nginx needed
for downloads), exposes Postgres on `localhost:5432`, and enables
`--reload` for live code changes.

### Option: run the prebuilt image instead of building

If you just want a server running — no source edits, no local build — skip
`--build` and pull the published image from Docker Hub instead:

```bash
cp .env.example .env
cp secrets/firebase-service-account.json.example secrets/firebase-service-account.json
# edit .env: set a real POSTGRES_PASSWORD, JWT_SECRET_KEY, SERVER_SETUP_TOKEN
docker compose pull db api
docker compose up -d db api
docker compose logs -f api   # wait for "Application startup complete"
```

This uses whatever `API_IMAGE_TAG` is set to in `.env` (defaults to
`latest`, i.e. the newest tagged release — set it to a specific version
like `v1.2.0` to pin). The `docker-compose.override.yml` live-reload setup
above is for editing code and doesn't apply here since there's no local
source mounted; drop `MEDIA_SERVE_MODE=direct` / `ENABLE_DOCS=true` into
`.env` directly if you still want them.

Register your two accounts against the running server:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"a-strong-password","display_name":"Alice","setup_token":"<your SERVER_SETUP_TOKEN>"}'
```

### Running tests

```bash
pip install -e ".[dev]"
docker compose up -d db   # tests run against a real Postgres, not sqlite
pytest
```

---

## Database migrations

Migrations run automatically on container start (`docker/entrypoint.sh`
runs `alembic upgrade head` before starting Uvicorn) — you don't need to run
them by hand for a normal deploy or update.

To create a new migration after changing a model:

```bash
docker compose exec api alembic revision --autogenerate -m "describe the change"
docker compose exec api alembic upgrade head
```

Always read an autogenerated migration before applying it — Alembic is good
but not infallible, especially around enum types and generated columns.

To roll back one migration:

```bash
docker compose exec api alembic downgrade -1
```

---

## API documentation

The full OpenAPI schema and interactive Swagger UI are available at `/docs`
and `/api/v1/openapi.json` **only when `ENABLE_DOCS=true`** — intentionally
off by default in production. For local development:

```bash
# with docker-compose.override.yml.example copied in, this is already true
open http://localhost:8000/docs

```
