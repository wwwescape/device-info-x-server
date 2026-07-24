#!/bin/sh
# Restores a backup produced by backup_db.sh.
# DESTRUCTIVE: the dump was created with --clean --if-exists, so restoring
# drops and recreates every object it contains.
#
# Usage: ./scripts/restore_db.sh path/to/backup.sql.gz
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 path/to/backup.sql.gz"
  exit 1
fi
BACKUP_FILE="$1"

set -a
. ./.env
set +a

echo "This will REPLACE all data in the '$POSTGRES_DB' database. Ctrl+C now to abort."
sleep 5

gunzip -c "$BACKUP_FILE" | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "Restore complete. Restart the api container so it doesn't hold stale connections: docker compose restart api"
