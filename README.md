# Device Info X Server

Self-hosted backend for **Device Info X**, a private messaging app built for
exactly two partners. Everything — auth, pairing, chat, media, shared
calendar, birthdays/anniversaries, period tracking, and a Safe Locker — runs
on hardware you own. The only thing that ever leaves your network is a push
notification via Firebase Cloud Messaging, and even that never contains
message content.

This README assumes basic Linux comfort (editing a file, running commands
over SSH) but **zero prior experience with Firebase, Docker, or Nginx** —
every step is spelled out.

---

## Table of contents

1. [Architecture](#architecture)
2. [Tech stack](#tech-stack)
3. [Repository layout](#repository-layout)
4. [Prerequisites](#prerequisites)
5. [Environment variables](#environment-variables)
6. [Media type policy](#media-type-policy)
7. [Firebase setup](#firebase-setup)
8. [Local development](#local-development)
9. [Database migrations](#database-migrations)
10. [Deploying with Docker](#deploying-with-docker)
11. [Port forwarding and Dynamic DNS](#port-forwarding-and-dynamic-dns)
12. [HTTPS, Let's Encrypt, and the reverse proxy](#https-lets-encrypt-and-the-reverse-proxy)
13. [Coturn (TURN/STUN)](#coturn-turnstun)
14. [Pairing your two accounts](#pairing-your-two-accounts)
15. [Registering an account for your partner](#registering-an-account-for-your-partner)
16. [Setting up Period Tracker for your partner](#setting-up-period-tracker-for-your-partner)
17. [Resetting all data](#resetting-all-data)
18. [Resetting a forgotten password](#resetting-a-forgotten-password)
19. [Enabling and disabling guided tours](#enabling-and-disabling-guided-tours)
20. [Testing push notifications](#testing-push-notifications)
21. [CSV data import](#csv-data-import)
22. [Backups and restore](#backups-and-restore)
23. [Updating containers](#updating-containers)
24. [Logs](#logs)
25. [Troubleshooting](#troubleshooting)
26. [Security hardening](#security-hardening)
27. [Monitoring](#monitoring)
28. [Production recommendations](#production-recommendations)
29. [API documentation](#api-documentation)
30. [License](#license)
31. [Support](#support)

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
accounts, hard-capped — see [Environment variables](#environment-variables)).
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
clarity — see [HTTPS, Let's Encrypt, and the reverse proxy](#https-lets-encrypt-and-the-reverse-proxy).
"Router/firewall: port-forward" only applies if your host is behind NAT
without a public IP (typical for a home network). A VPS/cloud host with a
static public IP skips that step entirely and just opens the same ports in
its firewall/security group — see [Deploying with Docker](#deploying-with-docker).

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
[Deploying with Docker](#deploying-with-docker),
[Local development](#local-development), and
[Updating containers](#updating-containers).

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

## Prerequisites

- Any machine that can run **Docker Engine + the Compose plugin**
  (2GB+ RAM recommended) — a Linux VPS/cloud instance, a home server, a
  spare desktop, a single-board computer, a NAS with Docker support.
  Published images cover both `linux/amd64` and `linux/arm64`, so 64-bit
  ARM hardware is fully supported too.
- A domain name you can point at your server (a free [DuckDNS](https://www.duckdns.org/)
  subdomain works fine if you don't have one — see [Port forwarding and Dynamic DNS](#port-forwarding-and-dynamic-dns)).
- A free Google/Firebase account (for push notifications).
- SSH access (or a local terminal) on the machine you're deploying to.

---

## Environment variables

Copy the template and fill it in:

```bash
cp .env.example .env
```

Generate every secret with:

```bash
openssl rand -hex 32
```

| Variable | Purpose |
|---|---|
| `ENVIRONMENT`, `DEBUG` | Set `DEBUG=false` in production. |
| `ENABLE_DOCS` | Leave `false` in production — enables Swagger UI/ReDoc/raw OpenAPI schema, which you don't want publicly reachable. |
| `DOMAIN` | Your public hostname (DDNS or real domain). Used for Nginx's server_name/TLS cert paths and the TURN URLs. |
| `POSTGRES_*` | Database name/user/password. `POSTGRES_HOST` stays `db` (the Compose service name) unless you change the compose file. |
| `JWT_SECRET_KEY` | Signs access tokens. **Never reuse the example value.** |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` / `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes. Defaults (15 min / 30 days) are sane. |
| `PASSWORD_PEPPER` | Optional extra secret mixed into password hashing. Leave blank or set once and never change it (changing it invalidates every existing password hash). |
| `SERVER_SETUP_TOKEN` | The one-time shared secret both partners use to register their accounts. See [Pairing your two accounts](#pairing-your-two-accounts). |
| `MEDIA_ROOT` | Leave as `/data/media` — this is a path *inside* the api container, backed by the `media_data` Docker volume. |
| `MAX_IMAGE_SIZE_MB` / `MAX_VOICE_SIZE_MB` / `MAX_VIDEO_SIZE_MB` / `MAX_AVATAR_SIZE_MB` / `MAX_LOCKER_FILE_SIZE_MB` / `MAX_DOCUMENT_SIZE_MB` | Per-category upload caps — see [Media type policy](#media-type-policy) for which mime types each category accepts. If you raise these, also raise `client_max_body_size` in `nginx/nginx.conf`. |
| `MEDIA_SERVE_MODE` | `x-accel` in production (Nginx serves files). `direct` only for local dev without Nginx in front. |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Path to the Firebase service-account key *inside the container*. See [Firebase setup](#firebase-setup). |
| `TURN_STATIC_SECRET` | Shared secret between the api container and coturn. |
| `TURN_URLS` | Comma-separated TURN URLs handed to clients, e.g. `turn:yourdomain.duckdns.org:3478?transport=udp`. |
| `TURN_CREDENTIAL_TTL_SECONDS` | How long a TURN credential (from `GET /api/v1/turn/credentials`) stays valid. |

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

## Firebase setup

Firebase Cloud Messaging (FCM) is how this server tells the Android app
"you have something new" without ever putting message content in the push
payload. You need a Firebase **project**, an Android **app registration**
inside it, and a **service account key** for this server to authenticate
with. This whole section assumes you've never touched Firebase before.

### 1. Create a Firebase project

1. Go to <https://console.firebase.google.com/> and sign in with a Google
   account.
2. Click **Add project**.
3. Give it a name (e.g. `device-info-x`). Google Analytics is not needed —
   you can disable it.
4. Click **Create project** and wait for it to finish provisioning.

### 2. Register the Android application

This step belongs to the **Android app project**, not this server repo, but
it has to happen before the server config makes sense.

1. In the Firebase console, open your new project and click the Android
   icon ("Add app").
2. Enter the app's package name (this must exactly match the
   `applicationId` in the Android project's `build.gradle`).
3. Skip the optional nickname/SHA-1 fields unless the Android app needs
   them for something else (e.g. Google Sign-In — not required here).
4. Click **Register app**.

### 3. Download `google-services.json`

Firebase will offer a `google-services.json` file to download. **This file
goes into the Android app project** (`app/google-services.json`), not this
server. It's what lets the Android app receive FCM messages at all. This
server doesn't need it.

### 4. Create a service account (what *this server* needs)

1. In the Firebase console, click the gear icon → **Project settings**.
2. Open the **Service accounts** tab.
3. Click **Generate new private key**, confirm, and a `.json` file will
   download — something like `device-info-x-firebase-adminsdk-xxxxx.json`.
4. **Treat this file like a password.** It grants full admin access to your
   Firebase project's messaging (and other) APIs.

### 5. Put the key where the server can read it

```bash
mkdir -p secrets
cp ~/Downloads/device-info-x-firebase-adminsdk-xxxxx.json secrets/firebase-service-account.json
chmod 600 secrets/firebase-service-account.json
```

`docker-compose.yml` bind-mounts `./secrets/firebase-service-account.json`
into the `api` container at `/run/secrets/firebase-service-account.json`,
which is what `FIREBASE_SERVICE_ACCOUNT_JSON` in `.env` should point at (the
`.env.example` default already matches). The `secrets/` directory is
git-ignored — never commit this file.

If you skip this step entirely, the server starts up fine and logs a
warning (`FIREBASE_SERVICE_ACCOUNT_JSON not set — push notifications
disabled`) — everything else works, you just won't get push notifications
when the app is backgrounded.

### 6. Testing notifications

Once a device has called `POST /api/v1/devices` with its FCM registration
token (the Android app does this automatically after login), you can send
a manual test push two ways:

- **Firebase console**: Project → Engage → Messaging → "New campaign" →
  Notification → send a test message to the specific FCM token. This bypasses
  this server entirely and is the fastest way to confirm the *Android app*
  itself is receiving pushes correctly.
- **Trigger a real event**: send a message from one paired account while
  the other account's app is backgrounded — you should get a push within a
  few seconds. Check `docker compose logs -f api` for `FCM send failed` if
  nothing arrives.

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

## Deploying with Docker

These steps work on **any host with Docker Engine and the Compose
plugin** — a Linux VPS/cloud instance, a home server, whatever you've got.
They're written for a fresh Debian/Ubuntu-family Linux install (which
covers most VPS images and common home-server distros); asides below call
out where another distro or a home network specifically changes something.

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker   # or log out and back in
docker compose version   # confirm the compose plugin is present
```

`get.docker.com` supports most Linux distros (Debian, Ubuntu, Fedora,
CentOS, etc.) — see [docs.docker.com/engine/install](https://docs.docker.com/engine/install/)
if your distro isn't covered, or [Docker Desktop](https://www.docker.com/products/docker-desktop/)
for local testing on macOS/Windows.

### 2. Get the deployment files

You only need two files to run prebuilt images — `docker-compose.yml`
points at `wwwescape/device-info-x-server`,
`wwwescape/device-info-x-server-nginx`, and
`wwwescape/device-info-x-server-coturn` on Docker Hub, all built with this
repo's config already baked in:

```bash
mkdir -p device-info-x-server/secrets && cd device-info-x-server
curl -fsSLO https://raw.githubusercontent.com/wwwescape/device-info-x-server/master/docker-compose.yml
curl -fsSLO https://raw.githubusercontent.com/wwwescape/device-info-x-server/master/.env.example
curl -fsSLo secrets/firebase-service-account.json.example https://raw.githubusercontent.com/wwwescape/device-info-x-server/master/secrets/firebase-service-account.json.example
```

That third file matters even if you don't want push notifications yet —
without *something* already at `secrets/firebase-service-account.json`
before the `api` container's first start, Docker bind-mounts a directory
there instead of a file (since there's nothing to mount), which breaks
Firebase init in a much less obvious way than a missing file would. Step 3
below turns this `.example` into the real (empty-or-not) file Compose
expects.

If you'd rather build from source, want the `scripts/*.sh` helpers
(`init_letsencrypt.sh`, `backup_db.sh`, `restore_db.sh`, `renew_cert.sh`),
or just want to read the code, clone the whole repo instead — either works
with everything below:

```bash
sudo apt-get update && sudo apt-get install -y git   # or your distro's package manager
git clone https://github.com/wwwescape/device-info-x-server device-info-x-server
cd device-info-x-server
```

### 3. Configure

```bash
cp .env.example .env
nano .env   # fill in every secret and DOMAIN
```

At minimum set: `DOMAIN`, `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`,
`SERVER_SETUP_TOKEN`, `TURN_STATIC_SECRET`. Generate each with
`openssl rand -hex 32`. See [Firebase setup](#firebase-setup) for the
`secrets/firebase-service-account.json` file.

Turn the placeholder from step 2 into the real file Compose expects — an
empty file is fine if you don't want push notifications yet; the app logs
a warning and continues without FCM:

```bash
cp secrets/firebase-service-account.json.example secrets/firebase-service-account.json
```

### 4. Point a domain at your server first

Do this *before* starting containers — Let's Encrypt's HTTP-01 challenge
needs port 80 reachable from the internet.

- **Behind NAT with no public IP** (typical home network): set up port
  forwarding and Dynamic DNS — see
  [Port forwarding and Dynamic DNS](#port-forwarding-and-dynamic-dns)
  below, then come back here.
- **Static public IP** (most VPS/cloud hosts): skip DDNS, just point a
  real DNS A record at the IP, and open ports 443, 80, 3478 (tcp+udp), and
  49160–49200/udp in your provider's firewall/security group instead of a
  home router.

### 5. Bring up the database and API

Compiling from source takes a few minutes, more so on lower-powered
hardware. To skip that and pull every prebuilt
multi-arch image from Docker Hub instead (`db` uses the stock Postgres
image regardless; `api`, `nginx`, and `coturn` use this project's images):

```bash
docker compose pull
docker compose up -d db api
docker compose logs -f api   # wait for "Application startup complete", Ctrl+C to stop following
```

To build from source instead (e.g. you've made local changes):

```bash
docker compose up -d --build db api
docker compose logs -f api
```

### 6. Start Nginx (HTTP only, for the ACME challenge) and issue the certificate

```bash
docker compose up -d nginx
./scripts/init_letsencrypt.sh yourdomain.duckdns.org you@example.com
docker compose restart nginx
```

If you didn't clone the repo and don't have `scripts/init_letsencrypt.sh`,
run the command it wraps directly instead:

```bash
docker compose up -d nginx
docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d yourdomain.duckdns.org \
  --email you@example.com \
  --agree-tos --no-eff-email --non-interactive
docker compose restart nginx
```

### 7. Start everything else

```bash
docker compose up -d
docker compose ps   # all services should show healthy/running
```

Your server is now reachable at `https://yourdomain.duckdns.org`. Point the
Android app's base URL at it, then follow
[Pairing your two accounts](#pairing-your-two-accounts).

### 8. (Recommended) Run as a systemd service

Docker Compose already restarts containers on failure (`restart:
unless-stopped`) and on Docker daemon start, which itself is enabled by
default after installing via `get.docker.com`. No additional systemd unit
is required for the containers themselves — a host reboot brings
everything back up automatically once Docker starts, regardless of what
kind of host it is.

---

## Port forwarding and Dynamic DNS

This section only applies if your server is behind NAT without a public
IP — the common case for a home network. Two things are needed for the
outside world to reach it. **If you're on a
VPS/cloud host with a static public IP, skip this whole section** — point
a real DNS A record at it and open the ports below in your provider's
firewall/security group instead.

### Dynamic DNS (DuckDNS example)

Most home internet connections don't have a static IP, so you need a
hostname that updates itself when your IP changes.

1. Go to <https://www.duckdns.org/> and sign in (GitHub/Google/etc.).
2. Create a subdomain, e.g. `device-info-x` → `device-info-x.duckdns.org`.
3. Copy your DuckDNS token from the dashboard.
4. Keep it updated with a cron job:

```bash
mkdir -p ~/duckdns
cat > ~/duckdns/duck.sh <<'EOF'
#!/bin/sh
curl -s "https://www.duckdns.org/update?domains=device-info-x&token=<your-token>&ip=" >/dev/null
EOF
chmod +x ~/duckdns/duck.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh") | crontab -
```

Use the resulting hostname (`device-info-x.duckdns.org`) as `DOMAIN` in
`.env`. Any other DDNS provider (No-IP, Cloudflare Tunnel, a router with
built-in DDNS, etc.) works the same way — just update `DOMAIN` accordingly.

### Port forwarding

On your router's admin page, forward these to your server's local IP (set
a DHCP reservation for it first so its local IP doesn't change):

| Port | Protocol | Purpose |
|---|---|---|
| 443 | TCP | HTTPS (API + WebSocket) |
| 80 | TCP | Let's Encrypt HTTP-01 challenge only |
| 3478 | TCP + UDP | TURN/STUN signaling |
| 49160–49200 | UDP | TURN media relay range |

---

## HTTPS, Let's Encrypt, and the reverse proxy

Nginx terminates TLS and reverse-proxies two things to the `api` container:

- `/api/*` → plain HTTP proxy
- `/ws` → WebSocket upgrade (`Upgrade`/`Connection` headers, 1-hour read
  timeout since connections are long-lived)

It also serves downloaded media directly via `X-Accel-Redirect`: the api
container authorizes a `/api/v1/media/{id}/download` request, then responds
with a header telling Nginx to stream the actual bytes from the read-only
`media_data` mount — the file's bytes never pass through Python.

Certificates come from Let's Encrypt via the `certbot` container using the
HTTP-01 **webroot** method: Nginx serves `/.well-known/acme-challenge/`
from a shared volume, and `certbot` proves domain ownership by writing a
file there that Let's Encrypt fetches over port 80. The `certbot` service
runs a renewal-check loop every 12 hours (a no-op unless the cert is within
its ~30-day renewal window); nothing to schedule yourself.

First issuance is manual — see step 6 of the deploy steps above, or
`scripts/init_letsencrypt.sh`. Nginx's config template
(`nginx/templates/app.conf.template`) is rendered at container start with
your `DOMAIN` substituted in, using the official Nginx image's built-in
envsubst mechanism.

**Note on coturn/TURN:** TURN traffic (UDP relay) is *not* proxied through
Nginx — it's exposed directly on ports 3478 and 49160-49200/udp. TLS-secured
TURN (`turns:`) isn't wired up in this scaffold; see
[Coturn (TURN/STUN)](#coturn-turnstun).

---

## Coturn (TURN/STUN)

Coturn is included as infrastructure scaffolding for a future WebRTC voice/
video calling feature — **no call-signaling is implemented in this version**
(no offer/answer/ICE exchange over the WebSocket). What *is* here:

- The `coturn` container itself, configured via `coturn/turnserver.conf` +
  CLI args in `docker-compose.yml` (realm, server name, and the shared
  `TURN_STATIC_SECRET`, all sourced from `.env`).
- `GET /api/v1/turn/credentials` — an authenticated endpoint that returns
  short-lived TURN credentials (HMAC-signed per coturn's REST API auth
  mechanism), so a future client can obtain working TURN credentials
  without any server changes.

If you don't plan to add calling, you can simply not forward coturn's ports
and leave the container running idle — it costs nothing to have it up.

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
  `./scripts/backup_db.sh` first — see [Backups and restore](#backups-and-restore).
- Registration is hard-capped at 2 accounts (see
  [Environment variables](#environment-variables)), so after a reset both
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
  set).` — see [Firebase setup](#firebase-setup).

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
[`samples/period_day_logs_example.csv`](samples/period_day_logs_example.csv) and
[`samples/calendar_events_example.csv`](samples/calendar_events_example.csv).

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
[Updating containers](#updating-containers).

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
itself has no per-item ownership (see [Architecture](#architecture)).

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

---

## Backups and restore

These helper scripts live in `scripts/` — if you deployed via [the minimal,
no-clone path](#2-get-the-deployment-files), clone the repo to get them
(they're plain `pg_dump`/`psql` wrappers, nothing that needs building).

```bash
./scripts/backup_db.sh                 # writes ./backups/device_info_x-<timestamp>.sql.gz
./scripts/backup_db.sh /mnt/usb-drive  # or any other output directory
```

This only backs up the **database**. Uploaded media (images, voice notes,
avatars, Safe Locker files) lives separately in the `media_data` Docker
volume — back that up too if it matters to you, using the companion script:

```bash
./scripts/backup_media.sh                 # writes ./backups/device_info_x-media-<timestamp>.tar.gz
./scripts/backup_media.sh /mnt/usb-drive  # or any other output directory
```

(The volume name is hardcoded in the script as
`device-info-x-server_media_data` — it comes from `docker-compose.yml`'s
top-level `name:` field, so it's always that regardless of what directory
you deployed into. Confirm with `docker volume ls` if unsure.)

To restore a database backup:

```bash
./scripts/restore_db.sh backups/device_info_x-20260101-120000.sql.gz
```

This is destructive — it drops and recreates everything in the dump
(`pg_dump --clean --if-exists` was used to create it). There's no
confirmation prompt beyond a 5-second pause; make sure you have the right
file.

To restore a media backup:

```bash
./scripts/restore_media.sh backups/device_info_x-media-20260101-120000.tar.gz
```

Unlike the database restore, this is additive — files are extracted on top
of whatever's already in the volume (same-named files are overwritten,
nothing extra is deleted). It's meant for restoring onto a fresh volume on a
new server (e.g. moving to a new VPS: `docker run -v` creates the named
volume automatically if it doesn't exist yet, so this can run before
`docker compose up` has ever touched the target host), not for layering
onto a live deployment.

**Moving to a new server?** Copy `docker-compose.yml` and `.env` over (see
[Deploying with Docker](#deploying-with-docker)), then run
`restore_db.sh` and `restore_media.sh` on the new host before starting the
`api` container for the first time.

**Recommendation:** put `backup_db.sh` (and `backup_media.sh`, if you have
media worth keeping) on a daily cron job writing to external/network
storage, not just the same disk as the live database.

---

## Updating containers

If you're running prebuilt images (the default —
[Local development](#local-development) / step 5 of the deploy steps above),
`nginx`/`coturn` config updates ship inside their images now too, so a
plain pull picks up everything — no `git pull` needed even if you never
cloned the repo:

```bash
docker compose pull     # fetches the latest api/nginx/coturn images plus postgres/certbot
docker compose up -d
docker compose logs -f api   # confirm migrations ran and startup succeeded
```

If you cloned the repo and changed `docker-compose.yml` itself (not just
`nginx/`/`coturn/` config, which no longer needs this), `git pull` that
first as usual.

If you're building from source instead:

```bash
git pull
docker compose build
docker compose up -d
docker compose logs -f api
```

`docker/entrypoint.sh` runs `alembic upgrade head` automatically on every
container start, so a normal update never requires a manual migration step.

---

## Logs

```bash
docker compose logs -f api      # application logs
docker compose logs -f nginx    # access/error logs
docker compose logs -f db       # Postgres logs
docker compose logs -f certbot  # renewal attempts
docker compose logs -f coturn   # TURN server logs
```

Add `--tail 200` to limit scrollback, or `--since 1h` for a time window.

---

## Troubleshooting

**`docker compose up` fails on the `api` service with a database connection
error.** The `api` service waits for `db`'s healthcheck (`pg_isready`)
before starting, so this usually means Postgres itself failed to start —
check `docker compose logs db` and confirm `POSTGRES_PASSWORD` in `.env`
matches what the volume was initialized with (Postgres only applies
`POSTGRES_PASSWORD` on first init — if you change it later without wiping
the `pgdata` volume, the old password stays in effect).

**Nginx won't start / certificate errors.** Nginx's HTTPS server block
requires a certificate to already exist at
`/etc/letsencrypt/live/$DOMAIN/`. Run `scripts/init_letsencrypt.sh` (or the
equivalent `docker compose run --rm --entrypoint certbot ...` command if
you didn't clone the repo — see step 6 of the deploy walkthrough) before
starting `nginx` with the full compose stack.

**Let's Encrypt issuance fails ("Connection refused" / "timeout").** Port 80
isn't reachable from the internet — double check port forwarding (or your
cloud firewall/security group on a VPS), that nothing is blocking
outbound-initiated inbound connections, and that `DOMAIN` in `.env`
actually resolves to your current public IP
(`dig +short yourdomain.duckdns.org`).

**Push notifications never arrive.** Check `docker compose logs api | grep
FCM`. Common causes: `FIREBASE_SERVICE_ACCOUNT_JSON` not mounted/misnamed,
the service account key revoked in the Firebase console, or the device
never called `POST /api/v1/devices` (check the `devices` table).

**WebSocket connects then immediately closes with code 1008.** That's the
server rejecting an invalid/expired/missing `Authorization: Bearer` header
on the handshake — confirm the access token hasn't expired (15 min default)
and that the client is sending it as a header, not a query parameter.

**"registration is closed" on `/auth/register`.** By design — this server
enforces a hard cap of 2 accounts. If you need to start over, see
[Resetting all data](#resetting-all-data) — there's no API for this,
intentionally.

**A container fails to start with `... not a directory` / `IsADirectoryError`,
mentioning a path you expected to be a file.** This is a bind-mount source
that doesn't exist on the host — Docker auto-creates missing bind-mount
sources as empty *directories*, so if the container's side expects a file
(like `secrets/firebase-service-account.json`) the mismatch fails at
startup. Fixed by making sure the referenced host path actually exists as
a file before starting the container: `rm -rf` the wrongly-created
directory, put a real (even empty) file at that path, then `docker compose
up -d --force-recreate <service>` — a plain restart won't pick up the fix,
since the bind was already resolved at container creation.

---

## Security hardening

- **Firewall.** Only open the ports listed in
  [Port forwarding](#port-forwarding-and-dynamic-dns) — nothing else needs
  to be internet-facing. `sudo apt-get install ufw && sudo ufw allow 22,80,443,3478/tcp && sudo ufw allow 3478,49160:49200/udp && sudo ufw enable`
  (adjust 22 to your actual SSH port).
- **SSH.** Disable password auth, use key-based login only
  (`PasswordAuthentication no` in `/etc/ssh/sshd_config`), and consider
  moving off port 22.
- **fail2ban.** Recommended as a second layer on top of the app's built-in
  in-process rate limiter on `/auth/login` and `/auth/register` (which is
  process-local and resets on restart). `sudo apt-get install fail2ban` and
  point a jail at Nginx's access log for repeated 401s.
- **Rotate `SERVER_SETUP_TOKEN`** to something you actually forget once
  both accounts are registered — it's useless after that point anyway
  since the server hard-caps at 2 accounts.
- **Keep the `secrets/` directory and `.env` off any backup destination
  that isn't encrypted at rest.**
- **Never set `ENABLE_DOCS=true` in production** — it exposes the full
  OpenAPI schema and interactive Swagger UI.
- **Keep containers updated** — see [Updating containers](#updating-containers).
  Subscribe to security advisories for `postgres`, `nginx`, and `coturn` base
  images if you want to stay ahead of CVEs rather than just periodically
  pulling.

---

## Monitoring

This is a 2-user personal server — full observability stacks (Prometheus/
Grafana) are almost certainly overkill, but at minimum:

- `docker compose ps` — all services should show `healthy` (db, api) or
  `running` (nginx, certbot, coturn) at a glance.
- `GET /api/v1/health/live` and `GET /api/v1/health/ready` — liveness (process
  up) vs readiness (process up *and* database reachable). Point an uptime
  checker (e.g. a free [UptimeRobot](https://uptimerobot.com/) monitor) at
  `https://yourdomain/api/v1/health/ready` if you want to be notified when
  the server goes down.
- `docker stats` — quick CPU/memory sanity check, especially useful on
  lower-powered hardware.
- Disk space — media and Postgres data both grow over time; `df -h`
  periodically, or a cron job that alerts below a threshold. Worth
  watching closer on smaller/slower storage than a large SSD/cloud volume.

---

## Production recommendations

- **Don't scale Uvicorn workers past 1.** The WebSocket connection manager
  and the in-process auth rate limiter both hold state in a single
  process's memory with no cross-process pub/sub — see the comment in
  `docker/entrypoint.sh`. If you ever need more throughput than one process
  gives you (unlikely for 2 users), that requires adding Redis-backed pub/
  sub first, not just bumping `UVICORN_WORKERS`.
- **Back up before every update** that includes a database migration —
  `./scripts/backup_db.sh` is cheap insurance.
- **Test restores occasionally**, not just backups — an untested backup is
  a guess, not a plan.
- **Keep `MEDIA_SERVE_MODE=x-accel` in production** — the `direct` mode
  streams every download through Python and exists purely for local dev
  convenience.
- **Prefer SSD/NVMe storage over SD cards or USB flash drives** for the
  Postgres/media volumes if your hardware gives you the choice — flash
  media like that degrades under sustained write load, and Postgres writes
  constantly even at idle (WAL checkpoints).

---

## API documentation

The full OpenAPI schema and interactive Swagger UI are available at `/docs`
and `/api/v1/openapi.json` **only when `ENABLE_DOCS=true`** — intentionally
off by default in production. For local development:

```bash
# with docker-compose.override.yml.example copied in, this is already true
open http://localhost:8000/docs

```
## License

GPL-3.0 — see `LICENSE`.

## Support

If you find Device Info X useful, consider buying me a coffee:

[<img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="40" />](https://buymeacoffee.com/wwwescape)