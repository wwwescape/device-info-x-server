"""Which server build is running — the server's counterpart to the app's `BUILD_TIMESTAMP`
(`app/build.gradle.kts`), shown on the status page (`app/api/status_page.py`).

Set by hand right before every force-push/deploy of a new build, same as the app's: `YYYY-MM-DD-NNNN`
(date + a per-day counter). Deliberately a constant in the source rather than derived from git or
stamped in by the Docker build — no reliance on the build environment, and a self-hoster building
the image locally gets the same value as the published one. The package `version` in
pyproject.toml stays at 0.0.1, mirroring the app's `versionName`.
"""

BUILD_TIMESTAMP = "2026-10-18-0003"
