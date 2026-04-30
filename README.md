# 🎓 Student Events Telegram Bot

A refined, menu-driven Telegram bot for managing university student events without the noise. It replaces repetitive group chat announcements with a persistent, auto-updating event dashboard.

## ✨ Core Features

- **Event Dashboard**: Each registered group chat has one persistent dashboard message that the bot updates automatically.
- **Menu-Driven UI**: Clean interaction via `InlineKeyboard` menus (My Events, Favorites, Admin Panel).
- **Owner Management**: Users can view, manage, and edit their own submitted events.
- **Smart Moderation**:
  - Edits create a "draft" that requires moderator approval before merging.
  - Mandatory rejection reasons: Creators receive specific feedback if a submission is denied.
- **Flexible Submission**: Supports titles, descriptions, dates, times, locations, and optional posters.
- **Security**: Strict private-chat restrictions for startup commands to prevent group chat clutter.
- **Safety**: Robust HTML escaping for all user-generated content and strict date/time validation (DD.MM.YYYY).

## 🛠 Tech Stack

- **Framework**: [aiogram 3](https://docs.aiogram.dev/) (Asynchronous Telegram Bot API)
- **Database**: [PostgreSQL](https://www.postgresql.org/) with [SQLAlchemy 2.0](https://www.sqlalchemy.org/)
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Storage**: [Redis](https://redis.io/) for FSM (Finite State Machine)
- **Deployment**: Docker & Docker Compose

## 📁 Project Structure

```text
├── app/
│   ├── handlers/        # Bot command and callback handlers
│   ├── models/          # SQLAlchemy database models
│   ├── services/        # Business logic (Dashboard, Events, Users)
│   ├── db/              # Database session and engine setup
│   ├── middlewares/     # AIogram middlewares (DB session injection)
│   ├── config.py        # Environment configuration
│   └── main.py          # Bot entrypoint
├── alembic/             # Database migration versions
├── scripts/             # Utility scripts (seed categories, etc.)
├── Dockerfile           # Bot containerization
└── docker-compose.yml   # Infrastructure (DB, Redis, Bot)
```

## 🚀 Quick Start Guide

Follow these steps to run the bot locally with your own token:

### 1. Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed.
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather).

### 2. Environment Setup
Clone the repository and create a `.env` file:
```bash
cp .env.example .env
```
Edit the `.env` file and fill in:
- `BOT_TOKEN`: Your token from BotFather.
- `ADMIN_IDS`: Your Telegram User ID (and any others) in `[123456]` format.
- `MODERATOR_CHAT_ID`: Your Telegram User ID (or a group ID) where moderation requests will go.

### 3. Launch Services
Start the database, redis, and the bot using Docker:
```bash
docker compose up -d
```

### 4. Initialize Database
Run the migrations and seed the initial event categories:
```bash
# Apply migrations
docker compose exec bot alembic upgrade head

# Seed categories (Engineering, Hackathons, etc.)
docker compose exec bot python scripts/seed_categories.py
```

### 5. Start Using the Bot
- **Private Chat**: Send `/start` to the bot to open the main menu.
- **Group Dashboard**: Add the bot to a group, promote it to admin, and send `/register_chat` followed by `/dashboard`.

### Monitoring
Check logs to ensure everything is running smoothly:
```bash
docker compose logs -f bot
```
