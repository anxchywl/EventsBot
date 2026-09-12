#!/bin/sh
# Logical backup of the events_bot Postgres database.
#
# This project ran without any backup service at all until 2026-09-12 — it was
# the only database on the shared host with nothing protecting it.
#
# Runs its own loop as PID 1 rather than under crond. crond passes none of the
# container's environment to the jobs it starts, so a scheduled pg_dump sees no
# POSTGRES_HOST and dies on the first line, writing nothing, while the container
# carries on reporting healthy. That is exactly how the sibling muto project
# lost a month of backups. A supervised loop inherits the environment and puts
# any failure in `docker logs`.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"

log() { echo "$(date -Iseconds) $*"; }

run_once() {
    ts=$(date +%Y%m%d-%H%M%S)
    out="$BACKUP_DIR/events_bot-$ts.dump"
    tmp="$out.partial"

    # -Fc keeps selective restore available via pg_restore. Written to .partial
    # first so a crash mid-dump cannot leave a truncated file sitting there
    # looking like a valid backup.
    if ! pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$tmp" 2>&1; then
        log "ERROR pg_dump failed"
        rm -f "$tmp"
        return 1
    fi

    # A dump that pg_restore cannot read is not a backup. Verify before it is
    # allowed to count as one, and before it can displace an older good dump.
    if ! pg_restore --list "$tmp" >/dev/null 2>&1; then
        log "ERROR dump failed verification, discarding"
        rm -f "$tmp"
        return 1
    fi

    mv "$tmp" "$out"
    chmod 600 "$out"
    log "backup ok: $(basename "$out") ($(du -h "$out" | cut -f1))"

    # Prune only after a new dump has been written and verified, so a failing
    # backup can never be the thing that ages out the last good one.
    find "$BACKUP_DIR" -maxdepth 1 -name 'events_bot-*.dump' -mtime "+$RETENTION_DAYS" -print -delete 2>/dev/null |
        while read -r old; do log "pruned $(basename "$old")"; done

    # Leave any interrupted dumps from a previous crash behind rather than
    # accumulating them forever.
    find "$BACKUP_DIR" -maxdepth 1 -name '*.partial' -mmin +120 -delete 2>/dev/null || true
    return 0
}

# `backup.sh once` is the manual/one-shot path; no argument runs the loop.
if [ "${1:-}" = "once" ]; then
    run_once
    exit $?
fi

log "backup loop started (interval ${INTERVAL}s, retention ${RETENTION_DAYS}d)"
while true; do
    run_once || log "backup cycle failed; retrying next interval"
    sleep "$INTERVAL"
done
