#!/bin/sh
# A backup right now, into backups/manual (the `backup` service makes the daily ones by itself):
# a database dump plus the HTML reports, checked by restoring the dump into a scratch database.
#   ./deploy/backup.sh
# Production: COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml" ./deploy/backup.sh
set -eu
cd "$(dirname "$0")/.."
COMPOSE=${COMPOSE:-docker compose}
$COMPOSE run --rm --no-deps -T backup sh /opt/backup/backup.sh now "${1:-manual}"
