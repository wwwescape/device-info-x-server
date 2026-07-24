#!/bin/sh
# Tars up the media_data Docker volume (uploaded images, voice notes, avatars, Safe Locker
# files) into a timestamped, gzip-compressed archive. Companion to backup_db.sh, which only
# covers the database — see README's "Backups and restore" section for why both are needed.
#
# Usage: ./scripts/backup_media.sh [output-dir]
set -e

OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"

# Fixed regardless of what directory you deployed into — comes from docker-compose.yml's
# top-level `name:` field, not the current directory name.
VOLUME_NAME="device-info-x-server_media_data"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUT_FILE="device_info_x-media-$TIMESTAMP.tar.gz"

docker run --rm \
  -v "$VOLUME_NAME":/data:ro \
  -v "$(cd "$OUT_DIR" && pwd)":/backup \
  alpine tar czf "/backup/$OUT_FILE" -C /data .

echo "Media backup written to $OUT_DIR/$OUT_FILE"
