#!/bin/bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.prod.yml}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-events_bot}"
ENV_FILE="${ENV_FILE:-.env}"
TIMEOUT_SECONDS="${HEALTHCHECK_TIMEOUT_SECONDS:-120}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
err() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: $*" >&2; exit 1; }

[ -f "${COMPOSE_FILE}" ] || err "Compose file not found: ${COMPOSE_FILE}"

COMPOSE_ARGS=(-p "${COMPOSE_PROJECT_NAME}" -f "${COMPOSE_FILE}")
if [ -f "${ENV_FILE}" ]; then
    COMPOSE_ARGS=(--env-file "${ENV_FILE}" "${COMPOSE_ARGS[@]}")
fi

compose() {
    docker compose "${COMPOSE_ARGS[@]}" "$@"
}

container_id() {
    compose ps -q "$1"
}

health_status() {
    local id
    id=$(container_id "$1")
    [ -n "${id}" ] || return 1
    docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${id}"
}

wait_for_healthy() {
    local service="$1"
    local deadline=$((SECONDS + TIMEOUT_SECONDS))
    local status
    while [ "${SECONDS}" -lt "${deadline}" ]; do
        status=$(health_status "${service}" 2>/dev/null || true)
        if [ "${status}" = "healthy" ] || [ "${status}" = "running" ]; then
            log "${service} is ${status}"
            return 0
        fi
        sleep 3
    done
    status=$(health_status "${service}" 2>/dev/null || true)
    err "${service} did not become healthy, last status: ${status:-missing}"
}

log "Verifying service health..."
for service in postgres redis web bot; do
    wait_for_healthy "${service}"
done

log "Verifying PostgreSQL..."
compose exec -T postgres pg_isready -U "${POSTGRES_USER:-events_bot}" -d "${POSTGRES_DB:-events_bot}" >/dev/null

log "Verifying Redis..."
compose exec -T redis sh -c 'REDISCLI_AUTH="${REDIS_PASSWORD}" redis-cli ping' | grep -qx "PONG"

log "Verifying FastAPI health and Mini App shell..."
compose exec -T web python - <<'PY'
import json
import urllib.request

health = json.load(urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5))
if health.get("status") != "ok":
    raise SystemExit("health endpoint returned an unexpected payload")

html = urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5).read(2000).decode("utf-8", "ignore")
if "<html" not in html.lower() and "<!doctype html" not in html.lower():
    raise SystemExit("mini app shell did not load")
PY

log "Verifying Alembic state..."
compose exec -T web alembic -c backend/alembic.ini current >/dev/null

log "Checking startup logs..."
if compose logs --since 2m web bot | grep -Eiq 'traceback|telegram polling conflict detected|application startup failed'; then
    err "startup logs contain critical errors"
fi

log "Health verification passed."
