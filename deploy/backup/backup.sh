#!/bin/sh
# TestHarbor backups. Runs inside the `backup` service (postgres:16-alpine, so pg_dump matches the server).
#
#   backup.sh daemon         every day at $BACKUP_AT: a daily backup (below); retried hourly when it fails
#   backup.sh now [KIND]     one backup now. KIND: daily (default; rotated into weekly/ and monthly/),
#                            manual, pre-restore. Each is a database dump plus an archive of the HTML reports,
#                            checked by restoring the dump into a scratch database.
#   backup.sh verify FILE    restore FILE into a scratch database, count its rows, drop it
#   backup.sh restore FILE   load FILE into the live database, in one transaction (deploy/restore.sh stops
#                            the backend first, and keeps a pre-restore backup of what is replaced)
#   backup.sh list           the backups there are
#   backup.sh health         the container healthcheck: the last daily backup worked and is recent
#
# FILE may be a path under the backups folder (daily/testharbor-….dump, or backups/daily/…) or "latest".
set -eu
umask 077

DIR=${BACKUP_DIR:-/backups}
REPORTS=${REPORTS_DIR:-/reports}
DB=${PGDATABASE:-testharbor}
SCRATCH="${DB}_restore_check"
AT=${BACKUP_AT:-03:15}
KEEP_DAILY=${KEEP_DAILY:-7}
KEEP_WEEKLY=${KEEP_WEEKLY:-4}
KEEP_MONTHLY=${KEEP_MONTHLY:-6}
KEEP_MANUAL=${KEEP_MANUAL:-10}

log() { echo "$(date -Iseconds) $*" >&2; }
die() { log "error: $*"; exit 1; }

# Files get the owner of the backups folder, so they can be copied off without root.
OWNER=$(stat -c %u:%g "$DIR" 2>/dev/null || echo 0:0)
own() { chown "$OWNER" "$@" 2>/dev/null || true; }

stamp_of() { basename "$1" .dump | sed 's/^testharbor-//'; }

# prune FOLDER KEEP: keep the newest KEEP dumps there, with their reports archives.
prune() {
  ls -1t "$1"/testharbor-*.dump 2>/dev/null | tail -n +"$(($2 + 1))" | while read -r f; do
    rm -f -- "$f" "$1/reports-$(stamp_of "$f").tar.gz"
    log "removed old $f"
  done
}

resolve() {
  case "$1" in
    latest) f=$(ls -1t "$DIR"/daily/testharbor-*.dump 2>/dev/null | head -n 1) ;;
    /*) f=$1 ;;
    *) f="$DIR/${1#backups/}" ;;
  esac
  [ -n "$f" ] && [ -f "$f" ] || die "no such backup: $1"
  echo "$f"
}

counts() {
  psql -d "$1" -Atc "SELECT 'schema ' || (SELECT version_num FROM alembic_version)
    || ', projects ' || (SELECT count(*) FROM projects) || ', cases ' || (SELECT count(*) FROM test_cases)
    || ', runs ' || (SELECT count(*) FROM test_runs) || ', results ' || (SELECT count(*) FROM test_results)
    || ', users ' || (SELECT count(*) FROM users)"
}

drop_scratch() { PGOPTIONS="-c client_min_messages=warning" psql -d postgres -qc "DROP DATABASE IF EXISTS \"$SCRATCH\"" >/dev/null; }

verify() {
  f=$(resolve "$1")
  drop_scratch
  psql -d postgres -qc "CREATE DATABASE \"$SCRATCH\""
  if ! pg_restore -d "$SCRATCH" --no-owner --exit-on-error "$f"; then
    drop_scratch
    die "$f does not restore"
  fi
  if ! got=$(counts "$SCRATCH"); then
    drop_scratch
    die "$f restored, but its tables are not all there"
  fi
  drop_scratch
  log "verified $f: $got (live now: $(counts "$DB"))"
}

backup() {
  kind=$1
  d="$DIR/$kind"
  mkdir -p "$d"
  own "$d"
  r=""
  stamp=$(date +%Y%m%d-%H%M%S)
  f="$d/testharbor-$stamp.dump"
  pg_dump -d "$DB" --format=custom --file="$f.tmp"
  mv "$f.tmp" "$f"
  own "$f"
  if [ "${BACKUP_REPORTS:-true}" = true ] && [ -d "$REPORTS" ]; then
    r="$d/reports-$stamp.tar.gz"
    tar -czf "$r.tmp" -C "$REPORTS" .
    mv "$r.tmp" "$r"
    own "$r"
  fi
  log "wrote $f ($(du -h "$f" | cut -f1))${r:+ and $(basename "$r") ($(du -h "$r" | cut -f1))}"

  if [ "${BACKUP_VERIFY:-true}" = true ] && ! (verify "$f"); then
    # Not counted as a backup (the daemon tries again); kept aside to look into.
    mv "$f" "$f.failed"
    [ -z "$r" ] || mv "$r" "$r.failed"
    die "the new backup failed its check; kept as $f.failed"
  fi

  case "$kind" in
    daily)
      for p in weekly monthly; do
        mkdir -p "$DIR/$p"
        own "$DIR/$p"
      done
      # A weekly copy when there is none from the last 6 days, a monthly one when this month has none.
      if [ -z "$(find "$DIR/weekly" -name 'testharbor-*.dump' -mtime -6)" ]; then
        ln "$f" "$DIR/weekly/"
        [ -z "$r" ] || ln "$r" "$DIR/weekly/"
      fi
      if ! ls "$DIR/monthly/testharbor-$(date +%Y%m)"* >/dev/null 2>&1; then
        ln "$f" "$DIR/monthly/"
        [ -z "$r" ] || ln "$r" "$DIR/monthly/"
      fi
      prune "$DIR/daily" "$KEEP_DAILY"
      prune "$DIR/weekly" "$KEEP_WEEKLY"
      prune "$DIR/monthly" "$KEEP_MONTHLY"
      ;;
    *) prune "$d" "$KEEP_MANUAL" ;;
  esac
  echo "$f"
}

daemon() {
  at=$(echo "$AT" | tr -d :)
  case "$at" in [0-2][0-9][0-5][0-9]) ;; *) die "BACKUP_AT must be HH:MM, got $AT" ;; esac
  log "daily backups at $AT ($(date +%Z)) into $DIR; keeping $KEEP_DAILY daily, $KEEP_WEEKLY weekly, $KEEP_MONTHLY monthly"
  last_try=0
  while :; do
    now=$(date +%H%M)
    # Due once the time has come and today has no backup yet (so a missed one runs after a restart);
    # after a failure, again an hour later.
    if [ "1$now" -ge "1$at" ] && ! ls "$DIR"/daily/testharbor-"$(date +%Y%m%d)"-*.dump >/dev/null 2>&1 \
      && [ $(($(date +%s) - last_try)) -ge 3600 ]; then
      last_try=$(date +%s)
      if sh "$0" now daily >/dev/null; then
        date -Iseconds >"$DIR/.last-ok" && own "$DIR/.last-ok"
        rm -f "$DIR/.last-error"
      else
        date -Iseconds >"$DIR/.last-error" && own "$DIR/.last-error"
        log "the daily backup FAILED; trying again in an hour"
      fi
    fi
    sleep 60
  done
}

health() {
  if [ -f "$DIR/.last-error" ]; then
    echo "the last daily backup failed at $(cat "$DIR/.last-error")"
    exit 1
  fi
  if [ -f "$DIR/.last-ok" ] && [ -z "$(find "$DIR/.last-ok" -mmin -1560)" ]; then
    echo "no daily backup since $(cat "$DIR/.last-ok")"
    exit 1
  fi
  echo ok
}

restore() {
  f=$(resolve "$1")
  # Check the file in a scratch database first, so a bad file never touches the live one.
  verify "$f"
  log "restoring $f into $DB"
  pg_restore -d "$DB" --clean --if-exists --no-owner --single-transaction --exit-on-error "$f"
  log "restored: $(counts "$DB")"
}

cmd=${1:-}
[ $# -gt 0 ] && shift
case "$cmd" in
  daemon) daemon ;;
  now) backup "${1:-daily}" ;;
  verify) verify "${1:?verify FILE}" ;;
  restore) restore "${1:?restore FILE}" ;;
  list) cd "$DIR" && find . -name '*.dump' -o -name '*.tar.gz' -o -name '*.failed' | sort | while read -r f; do
          echo "$(du -h "$f" | cut -f1)	${f#./}"; done ;;
  health) health ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
