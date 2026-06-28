# Production Deployment

Events Bot uses the same deployment model as Wished: GitHub Actions gates `main`, then SSHes into the production server, fast-forwards the server checkout, builds Docker images on the server, runs Alembic migrations, restarts Compose services, and verifies health.

## Current Wished Pipeline

Wished deploys from `.github/workflows/ci.yml`. Pull requests and pushes to `main` run backend dependency installation, Ruff linting, tests, and migration safety checks. A deploy job runs only for successful pushes to `main`.

Deployment uses `appleboy/ssh-action` with these GitHub Secrets:

- `SSH_HOST`
- `SSH_USER`
- `SSH_PRIVATE_KEY`
- `SSH_PATH`

On the server, the workflow changes into `SSH_PATH`, stashes local changes, runs `git pull --ff-only`, and executes `scripts/deploy.sh`.

Wished production runtime is defined in `docker-compose.prod.yml`. It builds images on the server, uses named Docker volumes for persistent data, never runs `docker compose down -v`, runs `alembic upgrade head` before restarting services, and starts containers with `docker compose up -d --remove-orphans`.

Wished’s Caddy container is the public ingress. Its production Caddyfile already contains an Events Bot route for `events.anxchywl.dev` and proxies it to `events_bot_web:8000` over the shared `wished_wished-app` Docker network.

## Events Bot Gaps Before This Change

Events Bot had a local `Dockerfile`, a local `docker-compose.yml`, a `/health` endpoint, Alembic migrations, and tests. It did not have:

- GitHub Actions
- production compose
- production Dockerfile
- migration safety check
- SSH deployment script
- rollback script behavior
- post-deploy health verification
- CI coverage reporting
- production deployment documentation

## Implemented Pipeline

The workflow in `.github/workflows/ci.yml` has four jobs:

- `test`: installs Python dependencies and CI tools, compiles Python, runs targeted Ruff static checks, verifies formatting for files touched by this change, type-checks security-critical modules, runs Bandit with current low-signal legacy findings skipped, and runs pytest with coverage
- `migration-safety`: scans Alembic `upgrade()` functions for destructive operations
- `docker`: validates `docker-compose.prod.yml` and builds production images
- `deploy`: runs only after all required jobs pass on pushes to `main`

The deploy job SSHes into the server, records the current git ref for rollback, stashes local changes, fetches `origin/main`, fast-forwards the server checkout, and runs `scripts/deploy.sh`.

## Production Runtime

`docker-compose.prod.yml` runs:

- `postgres`
- `redis`
- `bot`
- `web`

The `web` service joins the external `wished_wished-app` network so Wished’s existing Caddy container can route public traffic to `events_bot_web:8000`. Postgres and Redis stay isolated on the Events Bot data network.

Persistent data lives in named Docker volumes:

- `postgres-data`
- `redis-data`

## Deployment Flow

Normal deployment is automatic:

1. Developer pushes to GitHub `main`.
2. GitHub Actions runs tests, quality checks, migration safety, and Docker build.
3. If every required check passes, GitHub Actions SSHes into the production server.
4. The server checkout fast-forwards to `origin/main`.
5. `scripts/deploy.sh` validates migrations and Compose config.
6. Docker images build on the production server.
7. Alembic migrations run with `alembic upgrade head`.
8. Compose starts updated containers with `up -d --remove-orphans`.
9. `scripts/deploy-healthcheck.sh` verifies the deployment.

## Health Verification

The health script verifies:

- Postgres container is healthy
- Redis container is healthy
- Web container is healthy
- Bot container process is running
- PostgreSQL accepts connections with `pg_isready`
- Redis responds with `PONG`
- FastAPI `/health` returns `{"status":"ok"}`
- Mini App shell loads from `/`
- Alembic can report current revision
- recent web and bot logs do not contain critical startup errors

The Telegram bot cannot be fully validated without calling Telegram APIs, but the bot container healthcheck verifies the polling process is running and deployment logs are scanned for polling conflicts.

## Rollback Behavior

`scripts/deploy.sh` records the previous git ref through `DEPLOY_PREVIOUS_REF`. If build, migration, restart, or health verification fails, it:

1. checks out the previous ref
2. rebuilds the previous images
3. restarts Compose with the previous application code
4. runs health verification again
5. exits non-zero so GitHub Actions marks the deployment failed

Database migrations are not automatically downgraded. If a migration succeeded and the new application later failed health checks, rollback restores the previous application code against the migrated database. This is why the migration safety job blocks obvious destructive operations before production.

## Required GitHub Secrets

Create these repository secrets:

- `SSH_HOST`: production server hostname or IP
- `SSH_USER`: deployment user on the server
- `SSH_PRIVATE_KEY`: private SSH key with access to the server
- `SSH_PATH`: absolute path to the Events Bot checkout on the server

Application secrets live only in the server `.env`, not in GitHub Secrets.

## Required Server `.env`

Create `/path/to/events_bot/.env` on the server with:

```env
BOT_TOKEN=
SESSION_SECRET=
POSTGRES_PASSWORD=
REDIS_PASSWORD=
MINIAPP_BASE_URL=https://events.anxchywl.dev
ADMIN_IDS=[123456789]
MODERATOR_CHAT_ID=123456789
LOG_LEVEL=INFO
APP_TIMEZONE=Asia/Almaty
TELEGRAM_MINIAPP_SHORT_NAME=events
MINIAPP_SESSION_TTL_SECONDS=86400
TRUSTED_PROXY_IPS=
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_FROM=
EMAIL_CODE_TTL_MINUTES=10
EMAIL_RESEND_COOLDOWN_SECONDS=60
```

Generate `SESSION_SECRET` with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

## Server Prerequisites

On the production server:

1. Install Docker and Docker Compose.
2. Clone this repository to the path stored in `SSH_PATH`.
3. Create the production `.env`.
4. Ensure Wished production Caddy is running.
5. Ensure the Docker network `wished_wished-app` exists.
6. Ensure the Wished Caddyfile contains the Events Bot route for the production domain.
7. Run `bash scripts/setup-server.sh` from the Events Bot checkout.

## Manual Recovery

To inspect production:

```bash
cd /path/to/events_bot
docker compose --env-file .env -p events_bot -f docker-compose.prod.yml ps
docker compose --env-file .env -p events_bot -f docker-compose.prod.yml logs --tail=200 web bot
bash scripts/deploy-healthcheck.sh
```

To manually roll back to a known ref:

```bash
cd /path/to/events_bot
git checkout <known-good-ref>
bash scripts/deploy.sh
```

To check migrations:

```bash
cd /path/to/events_bot
bash scripts/check-migrations.sh alembic/versions
docker compose --env-file .env -p events_bot -f docker-compose.prod.yml run --rm web alembic current
```

## Test Coverage Report

Existing automated tests cover:

- Mini App Telegram init-data validation and session-token tampering
- protected endpoint rejection without valid sessions
- admin endpoint authorization
- Telegram event edit/delete ownership checks
- moderation access denial
- password and nickname validation
- public token and URL validation
- reminder offset validation
- event sync helpers
- event card escaping and deep links
- media cache helpers
- realtime review deletion payload filtering
- centralized Redis rate-limit behavior

Critical gaps that still need future tests:

- full email registration, verification, login, and password reset integration with a test database
- moderator approve/reject/request-changes happy paths
- event publication side effects into group dashboards
- reminder scheduler delivery loop with due reminders
- admin dashboard data authorization with persisted users
- analytics recording across open, share, registration, favorite, and reminder actions
- Docker-level startup tests against real Postgres and Redis in CI
- repo-wide Ruff formatting, because existing files predate a formatter baseline

New tests added in this change:

- centralized Redis rate limiter allows requests under limit
- centralized Redis rate limiter rejects requests over limit
- centralized Redis rate limiter repairs missing TTL

These replaced a stale private-memory-rate-limit test because favorites now use the shared Redis limiter.
