#!/bin/sh
# Put a backup back:
#   ./deploy/restore.sh latest                                  # the newest daily backup
#   ./deploy/restore.sh backups/daily/testharbor-20261123-031500.dump [--reports]
#
# 1. checks the file by restoring it into a scratch database (a bad file stops here, nothing is touched);
# 2. stops the backend and frontend, and backs up what is there now into backups/pre-restore;
# 3. replaces the database in one transaction (all or nothing), and with --reports the HTML reports too;
# 4. starts the backend and frontend again.
# Without asking: YES=1. Production: COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml" ./deploy/restore.sh …
set -eu
cd "$(dirname "$0")/.."
COMPOSE=${COMPOSE:-docker compose}
BACKUPS=${BACKUP_DIR:-$(sed -n 's/^BACKUP_DIR=//p' .env 2>/dev/null)}
BACKUPS=${BACKUPS:-./backups}
BACKUPS=${BACKUPS#./}
FILE=${1:?usage: deploy/restore.sh FILE|latest [--reports]}
FILE=${FILE#./}
FILE=${FILE#"$BACKUPS"/}  # the path inside the backups folder, as the backup container sees it
REPORTS=${2:-}
run() { $COMPOSE run --rm --no-deps -T backup sh /opt/backup/backup.sh "$@"; }

run verify "$FILE"
if [ "${YES:-}" != 1 ]; then
  printf 'Replace the TestHarbor database with %s? Type yes: ' "$FILE"
  read -r answer
  [ "$answer" = yes ] || { echo "Nothing changed."; exit 1; }
fi

$COMPOSE stop backend frontend
# Whatever happens below, start them again (each on its own, so one missing service doesn't keep the other down).
trap '$COMPOSE start backend; $COMPOSE start frontend' EXIT
run now pre-restore
run restore "$FILE"
if [ "$REPORTS" = --reports ]; then
  # The reports archive made together with the dump.
  # shellcheck disable=SC2012
  case "$FILE" in latest) dump=daily/$(cd "$BACKUPS/daily" && ls -1t -- testharbor-*.dump | head -n 1) ;; *) dump=$FILE ;; esac
  archive="$(dirname "$dump")/reports-$(basename "$dump" .dump | sed 's/^testharbor-//').tar.gz"
  $COMPOSE run --rm --no-deps -T backend sh -c \
    "test -f '/backups/$archive' && find /data/reports -mindepth 1 -delete && tar -xzf '/backups/$archive' -C /data/reports"
  echo "Reports restored from $archive"
fi
echo "Restored. Starting the backend and frontend."
