#!/bin/bash
set -euo pipefail

APP_USER="${APP_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-root}")}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
err() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: $*" >&2; exit 1; }

log "Setting up server for Events Bot production deployment"

if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "${APP_USER}"
    log "Docker installed, log out and back in if Docker permissions are not active"
else
    log "Docker already installed: $(docker --version)"
fi

if [ ! -f .env ]; then
    err ".env not found. Copy .env.example and fill required production values before deploying."
fi

REQUIRED_VARS=(
    BOT_TOKEN
    SESSION_SECRET
    POSTGRES_PASSWORD
    REDIS_PASSWORD
    MINIAPP_BASE_URL
    ADMIN_IDS
    MODERATOR_CHAT_ID
)

MISSING=0
for var in "${REQUIRED_VARS[@]}"; do
    value=$(grep -E "^${var}=" .env | cut -d= -f2- | tr -d '"' || true)
    if [ -z "${value}" ]; then
        echo "  MISSING: ${var}"
        MISSING=1
    fi
done

if [ "${MISSING}" -eq 1 ]; then
    err "Required environment variables are missing from .env"
fi

if ! docker network inspect wished_wished-app >/dev/null 2>&1; then
    err "Docker network wished_wished-app is missing. Start Wished production Caddy first."
fi

log "Server setup complete. Run: bash scripts/deploy.sh"
