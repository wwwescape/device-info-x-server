# Deployment

Everything needed to deploy and run Device Info X Server: configuration, Firebase, Docker, networking, TLS, TURN, backups, updates, and hardening. Back to the [README](../README.md).

## Contents

1. [Prerequisites](#prerequisites)
2. [Environment variables](#environment-variables)
3. [Firebase setup](#firebase-setup)
4. [Deploying with Docker](#deploying-with-docker)
5. [Port forwarding and Dynamic DNS](#port-forwarding-and-dynamic-dns)
6. [HTTPS, Let's Encrypt, and the reverse proxy](#https-lets-encrypt-and-the-reverse-proxy)
7. [Coturn (TURN/STUN)](#coturn-turnstun)
8. [Backups and restore](#backups-and-restore)
9. [Updating containers](#updating-containers)
10. [Logs](#logs)
11. [Troubleshooting](#troubleshooting)
12. [Security hardening](#security-hardening)
13. [Monitoring](#monitoring)
14. [Production recommendations](#production-recommendations)

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
| `SERVER_SETUP_TOKEN` | The one-time shared secret both partners use to register their accounts. See [Pairing your two accounts](administration.md#pairing-your-two-accounts). |
| `MEDIA_ROOT` | Leave as `/data/media` — this is a path *inside* the api container, backed by the `media_data` Docker volume. |
| `MAX_IMAGE_SIZE_MB` / `MAX_VOICE_SIZE_MB` / `MAX_VIDEO_SIZE_MB` / `MAX_AVATAR_SIZE_MB` / `MAX_LOCKER_FILE_SIZE_MB` / `MAX_DOCUMENT_SIZE_MB` | Per-category upload caps — see [Media type policy](development.md#media-type-policy) for which mime types each category accepts. If you raise these, also raise `client_max_body_size` in `nginx/nginx.conf`. |
| `MEDIA_SERVE_MODE` | `x-accel` in production (Nginx serves files). `direct` only for local dev without Nginx in front. |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Path to the Firebase service-account key *inside the container*. See [Firebase setup](#firebase-setup). |
| `TURN_STATIC_SECRET` | Shared secret between the api container and coturn. |
| `TURN_URLS` | Comma-separated TURN URLs handed to clients, e.g. `turn:yourdomain.duckdns.org:3478?transport=udp`. |
| `TURN_CREDENTIAL_TTL_SECONDS` | How long a TURN credential (from `GET /api/v1/turn/credentials`) stays valid. |
| `APK_DOWNLOAD_URL` | Where the Android client's Download button sends a partner running an out-of-date build. See [Recording the latest app build (in-app update check)](administration.md#recording-the-latest-app-build-in-app-update-check). Leave blank to disable the update card entirely. |

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
[Pairing your two accounts](administration.md#pairing-your-two-accounts).

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

Coturn backs the app's WebRTC voice/video calling feature (offer/answer/ICE
exchange rides the existing WebSocket — see `app/services/call_room_service.py`
and `app/ws/router.py`). What's here:

- The `coturn` container itself, configured via `coturn/turnserver.conf` +
  CLI args in `docker-compose.yml` (realm, server name, the shared
  `TURN_STATIC_SECRET`, and `TURN_EXTERNAL_IP`, all sourced from `.env`).
- `GET /api/v1/turn/credentials` — an authenticated endpoint that returns
  short-lived TURN credentials (HMAC-signed per coturn's REST API auth
  mechanism) for the client to use when starting a call.

**`TURN_EXTERNAL_IP` is required, not optional, once calling is in use.**
The `coturn` container runs on the `edge_net` Docker network rather than
`network_mode: host`, so it only knows its own internal container IP by
default (e.g. `172.20.x.x`) — without `TURN_EXTERNAL_IP` set to the host's
real public IPv4, coturn hands that unreachable internal address back as the
relay address in every TURN allocation. Calls between two devices that both
have a normal, port-forwardable connection to each other can still work off
STUN-derived candidates alone, but any call where a relay is actually
required — symmetric NAT, which is the common case on cellular data and many
public Wi-Fi networks — will silently fail end-to-end (signaling/room state
still succeeds, but no audio or video ever connects) with nothing in the
client logs pointing at coturn as the cause. Set it via
`curl -4 ifconfig.me` run *on the host itself*, then
`docker compose up -d coturn` to apply.

If you don't plan to add calling, you can simply not forward coturn's ports
and leave the container running idle — it costs nothing to have it up.

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
[Local development](development.md#local-development) / step 5 of the deploy steps above),
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
[Resetting all data](administration.md#resetting-all-data) — there's no API for this,
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
