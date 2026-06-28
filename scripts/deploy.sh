#!/bin/bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-events_bot}"
ENV_FILE="${ENV_FILE:-.env}"
PREVIOUS_REF="${DEPLOY_PREVIOUS_REF:-}"
ROLLBACK_ENABLED="${ROLLBACK_ENABLED:-true}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
err() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: $*" >&2; exit 1; }

for arg in "$@"; do
    case "$arg" in
        -v|--volumes) err "Refusing volume deletion flags" ;;
        --rmi) err "Refusing image removal flags" ;;
    esac
done

[ -f "${COMPOSE_FILE}" ] || err "Compose file not found: ${COMPOSE_FILE}"
[ -f "${ENV_FILE}" ] || err "Environment file not found: ${ENV_FILE}"

CURRENT_REF=$(git rev-parse HEAD)
if [ -z "${PREVIOUS_REF}" ]; then
    PREVIOUS_REF=$(git rev-parse HEAD~1 2>/dev/null || true)
fi

COMPOSE_ARGS=(-p "${COMPOSE_PROJECT_NAME}" -f "${COMPOSE_FILE}")
COMPOSE_ARGS=(--env-file "${ENV_FILE}" "${COMPOSE_ARGS[@]}")

compose() {
    docker compose "${COMPOSE_ARGS[@]}" "$@"
}

rollback() {
    local exit_code="$1"
    local line_no="$2"
    trap - ERR
    log "Deployment failed at line ${line_no} with exit code ${exit_code}"
    if [ "${ROLLBACK_ENABLED}" != "true" ] || [ -z "${PREVIOUS_REF}" ]; then
        err "Rollback skipped because no previous ref is available"
    fi

    log "Rolling back to ${PREVIOUS_REF}..."
    git checkout --quiet "${PREVIOUS_REF}"
    compose build
    compose up -d --remove-orphans
    bash scripts/deploy-healthcheck.sh
    err "Deployment rolled back to ${PREVIOUS_REF}; database migrations were not downgraded"
}

trap 'rollback "$?" "$LINENO"' ERR

log "Deploying Events Bot ${CURRENT_REF} with ${COMPOSE_FILE}"

log "Checking migration safety..."
bash scripts/check-migrations.sh alembic/versions

log "Validating Compose configuration..."
compose config --quiet

log "Pulling base images..."
compose pull --quiet 2>/dev/null || true

log "Building application images..."
compose build

log "Running database migrations..."
compose run --rm web alembic upgrade head

log "Starting services..."
compose up -d --remove-orphans

log "Running health verification..."
bash scripts/deploy-healthcheck.sh

trap - ERR
log "Deployment complete."
compose ps
