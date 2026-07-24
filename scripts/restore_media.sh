#!/bin/sh
# Restores a media backup produced by backup_media.sh into the media_data Docker volume.
# Companion to restore_db.sh, which only covers the database.
#
# Unlike restore_db.sh's --clean dump, this is ADDITIVE: files are extracted on top of
# whatever's already in the volume (same-named files are overwritten, nothing extra is
# deleted). Intended for restoring onto a fresh volume on a new server (e.g. moving to a new
# VPS) — `docker run -v` creates the named volume automatically if it doesn't exist yet, so
# this can run before `docker compose up` has ever touched the target host.
#
# Usage: ./scripts/restore_media.sh path/to/media-backup.tar.gz
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 path/to/media-backup.tar.gz"
  exit 1
fi
BACKUP_FILE="$1"
VOLUME_NAME="device-info-x-server_media_data"

echo "This will extract into the '$VOLUME_NAME' volume, overwriting any same-named files. Ctrl+C now to abort."
sleep 5

docker run --rm \
  -v "$VOLUME_NAME":/data \
  -v "$(cd "$(dirname "$BACKUP_FILE")" && pwd)":/backup:ro \
  alpine tar xzf "/backup/$(basename "$BACKUP_FILE")" -C /data

echo "Media restore complete."
