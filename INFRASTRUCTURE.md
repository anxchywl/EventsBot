# Student Events Bot — Infrastructure

Technical setup, environment, and deployment reference. For product and business rules see [PRODUCT.md](./PRODUCT.md). For agent coding rules see [AGENTS.md](./AGENTS.md).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | aiogram 3 |
| API and web server | FastAPI + Uvicorn |
| Database | PostgreSQL + SQLAlchemy (async) + Alembic |
| Cache | Redis |
| Mini App frontend | Vanilla JS and CSS |
| Runtime | Docker Compose |

---

## Repository Layout

```
events_bot/
├── app/                   # application code — see AGENTS.md for structure
├── alembic/               # database migrations
├── scripts/               # helper scripts (category seeding, deploy)
├── tests/                 # unit tests
├── docker-compose.yml
├── docker-compose.prod.yml
├── Dockerfile
├── Dockerfile.production
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

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in required values

docker compose up -d postgres redis
alembic upgrade head
python3 -m scripts.seed_categories
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

**Production**

```bash
docker compose up -d --build
```

Starts `postgres`, `redis`, `bot`, and `web` on port `8000`.

---

## Contributing

```bash
git checkout -b your-change
# make changes
python3 -m unittest discover tests
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
   bash scripts/setup-server.sh
   ```

### Production `.env`

Copy [`.env.example`](./.env.example) to `.env` on the server and fill in production values.

### Manual Recovery and Inspection

To inspect the production environment:
```bash
cd /path/to/events_bot
# Check running containers
docker compose --env-file .env -p events_bot -f docker-compose.prod.yml ps
# View application logs
docker compose --env-file .env -p events_bot -f docker-compose.prod.yml logs --tail=200 web bot
# Manually verify health
bash scripts/deploy-healthcheck.sh
```

To manually roll back to a known Git reference:
```bash
cd /path/to/events_bot
git checkout <known-good-commit>
bash scripts/deploy.sh
```
