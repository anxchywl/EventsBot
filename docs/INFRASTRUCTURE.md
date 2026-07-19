# Student Events Bot — Infrastructure

Technical setup, environment, and deployment reference. For product and business rules see [PRODUCT.md](./PRODUCT.md). For agent coding rules see [AGENTS.md](../AGENTS.md).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | aiogram 3 |
| API and web server | FastAPI + Uvicorn |
| Database | PostgreSQL + SQLAlchemy (async) + Alembic |
| Cache | Redis |
| Telegram Mini App | Vanilla JS and CSS |
| Events feature | Flutter (`flutter_events/`) and shared `app_ui/` package |
| Runtime | Docker Compose |

---

## Repository Layout

```
events_bot/
├── backend/               # Python application code and Alembic migrations
├── frontend/              # Mini App static assets
├── flutter_events/        # Flutter Events feature and standalone host
├── app_ui/                # shared Flutter design system package
├── docs/                  # product and infrastructure documentation
├── .github/               # CI/CD workflows
├── docker/                # Dockerfiles and Docker Compose files
├── deploy/                # deployment and healthcheck scripts
├── scripts/               # local utility scripts
├── tests/                 # backend and frontend tests
├── backend/pyproject.toml
├── backend/uv.lock
└── .env.example
```

---

## Local Development Setup

**Prerequisites**

- Python 3.12+
- Docker and Docker Compose
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram user ID for admin access

**Setup**

```bash
git clone https://github.com/anxchywl/events_bot
cd events_bot

cp .env.example .env
# fill in required values

docker compose -f docker/docker-compose.yml up -d postgres redis

cd backend
uv sync
source .venv/bin/activate
alembic -c alembic.ini upgrade head
PYTHONPATH=.:.. python3 -m scripts.seed_categories
```

**Running the bot**

```bash
python3 -m app.main
```

**Running the Mini App server**

```bash
uvicorn app.web.main:web_app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` to check the Mini App locally.

The Flutter Events feature is developed separately from the bot and Mini App
server. Its standalone host and Jas Wallet integration contract are documented
in [`flutter_events/README.md`](../flutter_events/README.md); it does not change
the Docker services described here.

**Production**

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Starts `postgres`, `redis`, `bot`, and `web` on port `8000`.

---

## Contributing

```bash
git checkout -b your-change
# make changes
cd backend
PYTHONPATH=. pytest ../tests/backend
```

When opening a pull request, include what changed, how you tested it, and screenshots if the UI changed.

---

## Production Deployment

The bot is deployed using GitHub Actions to SSH into the production server, build Docker images, run migrations, and verify health checks.

### Required GitHub Secrets

Create these repository secrets in GitHub:
- `SSH_HOST`: production server hostname or IP
- `SSH_USER`: deployment user on the server
- `SSH_PRIVATE_KEY`: private SSH key with access to the server
- `SSH_PATH`: absolute path to the checkout on the server

### Server Prerequisites

On the production server:
1. Install Docker and Docker Compose.
2. Clone this repository to `SSH_PATH`.
3. Copy `.env.example` to `.env` at `SSH_PATH` and fill in production values.
4. Ensure the shared Docker network `wished_wished-app` exists.
5. Configure your ingress proxy (e.g., Caddy) to route traffic to `events_bot_web:8000`.
6. Run the server setup script:
   ```bash
   bash deploy/setup-server.sh
   ```

### Production `.env`

Copy [`.env.example`](../.env.example) to `.env` on the server and fill in production values.

### Manual Recovery and Inspection

To inspect the production environment:
```bash
cd /path/to/events_bot
# Check running containers
docker compose --env-file .env -p events_bot -f docker/docker-compose.prod.yml ps
# View application logs
docker compose --env-file .env -p events_bot -f docker/docker-compose.prod.yml logs --tail=200 web bot
# Manually verify health
bash deploy/deploy-healthcheck.sh
```

To manually roll back to a known Git reference:
```bash
cd /path/to/events_bot
git checkout <known-good-commit>
bash deploy/deploy.sh
```
