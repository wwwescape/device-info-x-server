<h1 align="center">Device Info X Server</h1>

<p align="center">
  The self-hosted backend for <b>Device Info X</b>, a private space built for exactly two partners.
  Messaging, calls, a shared calendar, period tracking, notes, and a Safe Locker all run on
  hardware you own.
</p>

<p align="center">
  <a href="https://github.com/wwwescape/device-info-x-server/releases"><img src="https://img.shields.io/github/v/release/wwwescape/device-info-x-server.svg?style=flat-square" alt="GitHub release" /></a>
  <a href="https://github.com/wwwescape/device-info-x-server/commits/master"><img src="https://img.shields.io/github/last-commit/wwwescape/device-info-x-server.svg?style=flat-square" alt="GitHub last commit" /></a>
  <a href="https://github.com/wwwescape/device-info-x-server"><img src="https://img.shields.io/github/languages/code-size/wwwescape/device-info-x-server.svg?color=red&style=flat-square" alt="GitHub code size" /></a>
</p>

## Features

- **REST API and realtime gateway** — a versioned FastAPI API plus a WebSocket that delivers
  messages, receipts, typing, presence, calendar and Safe Locker changes, call signaling, and
  live location as they happen.
- **Two accounts, one couple** — registration needs your server setup token and is hard-capped
  at 2 accounts, paired with a short-lived one-time code.
- **Data storage & sync** — PostgreSQL holds messages (with full-text search), calendar events,
  period logs, notes, scheduled messages, Safe Locker items, and the call log. Phones keep only a
  cache, so logging in on a new phone restores everything.
- **Media handling** — photos, videos, voice notes, documents, avatars, and Safe Locker files,
  with per-type size limits, served by Nginx only after an access check.
- **Push notifications** — Firebase Cloud Messaging, always as a generic notice that never
  carries message content.
- **Background scheduler** — calendar, birthday, anniversary, and cycle reminders, holiday
  greetings, and scheduled messages, each delivered once.
- **Calling** — WebRTC voice and video call signaling, a bundled coturn (TURN/STUN) service with
  time-limited credentials, and a metadata-only call log.
- **Server-side helpers** — link previews fetched by the server, an optional KLIPY GIF proxy,
  and custom reactions and stickers served from your own folders.
- **Remotely managed content** — guided tours, What's New announcements, DIX AI Insights, and
  the app's update check, all managed from the server.
- **Admin CLI** — register accounts, reset passwords, send test notifications, import and export
  CSV data, and reset everything.

## Requirements

- A Linux host with Docker Engine and the Compose plugin (`linux/amd64` or `linux/arm64`,
  2 GB+ RAM recommended)
- A domain name pointed at it (a free [DuckDNS](https://www.duckdns.org/) subdomain works)
- Ports 80/443 (TCP), 3478 (TCP + UDP), and 49160–49200 (UDP) reachable from the internet
- A free Firebase project, for push notifications
- The **Device Info X** Android app on both phones

## Installation

Prebuilt multi-arch images are published to Docker Hub and GHCR, so a deploy needs only
`docker-compose.yml` and `.env` — no git clone:

- `wwwescape/device-info-x-server` — the API
- `wwwescape/device-info-x-server-nginx` — reverse proxy + TLS
- `wwwescape/device-info-x-server-coturn` — TURN/STUN

In short:

1. Download `docker-compose.yml`, `.env.example`, and
   `secrets/firebase-service-account.json.example` from this repo.
2. Copy `.env.example` to `.env` and set at least `DOMAIN`, `POSTGRES_PASSWORD`,
   `JWT_SECRET_KEY`, `SERVER_SETUP_TOKEN`, and `TURN_STATIC_SECRET` (generate each with
   `openssl rand -hex 32`).
3. Add your Firebase service-account key as `secrets/firebase-service-account.json`.
4. Point your domain at the server, start the database, API, and Nginx, and issue a Let's
   Encrypt certificate.
5. Run `docker compose up -d`, point both apps at `https://yourdomain`, and pair the two
   accounts.

The [deployment guide](docs/deployment.md) walks through every step, with no prior Docker,
Firebase, or Nginx experience assumed.

## Configuration

All settings live in `.env` — see [Environment variables](docs/deployment.md#environment-variables)
for every option, and [Firebase setup](docs/deployment.md#firebase-setup) for push
notifications. `KLIPY_API_KEY` (GIF search) and `APK_DOWNLOAD_URL` (in-app update check) are
optional.

## Documentation

| Guide                                           | What's in it                                                                                     |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [Deployment](docs/deployment.md)                | Configuration, Firebase, Docker, port forwarding and DNS, TLS, TURN, backups, updates, logs, troubleshooting, and hardening |
| [Administration](docs/administration.md)        | Pairing, registering accounts, Period Tracker setup, password and data resets, tours, What's New, DIX AI Insights, update checks, push testing, and CSV import/export |
| [Development](docs/development.md)              | Architecture, tech stack, repository layout, media type policy, local development, migrations, and API docs |

## Privacy & Security

- **One couple per deployment** — no multi-tenant hosting, no public sign-up.
- **No analytics or third-party telemetry.**
- **Limited outbound connections** — Firebase Cloud Messaging for push notifications, KLIPY only
  when you set a GIF API key, and link previews, which the server fetches so the linked sites
  never see your phone.
- **Hardened by default** — Argon2 password hashing, short-lived access tokens with revocable
  refresh tokens, rate-limited login and registration, TLS 1.2/1.3 with security headers, and
  API docs turned off in production.

See [Security hardening](docs/deployment.md#security-hardening) for firewall, SSH, and fail2ban
tips.

## License

GPL-3.0 — see [LICENSE](LICENSE).

## Support

If you find Device Info X Server useful, consider buying me a coffee:

[<img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="40" />](https://buymeacoffee.com/wwwescape)
