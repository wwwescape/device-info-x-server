#!/bin/sh
# Dumps the Postgres database to a timestamped, gzip-compressed, self-
# contained (--clean --if-exists) SQL file.
#
# Usage: ./scripts/backup_db.sh [output-dir]
set -e

OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"

set -a
. ./.env
set +a

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUT_FILE="$OUT_DIR/device_info_x-$TIMESTAMP.sql.gz"

docker compose exec -T db pg_dump --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUT_FILE"

echo "Backup written to $OUT_FILE"
