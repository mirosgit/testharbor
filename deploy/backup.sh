#!/bin/sh
# Dump the TestHarbor database to ./backups (keeps the newest $KEEP dumps).
# Cron example (daily 03:15):
#   15 3 * * * cd /opt/testharbor && ./deploy/backup.sh >> backups/backup.log 2>&1
set -eu
cd "$(dirname "$0")/.."
KEEP=${KEEP:-14}
mkdir -p backups
FILE="backups/testharbor-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U testharbor -d testharbor --format=custom > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"
echo "$(date -Iseconds) wrote $FILE ($(du -h "$FILE" | cut -f1))"
ls -1t backups/testharbor-*.dump | tail -n +"$((KEEP + 1))" | xargs -r rm --
