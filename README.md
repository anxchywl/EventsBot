# Student Events Telegram Bot

A Telegram bot for managing university student events without spamming group chats.

The main idea is simple: each Telegram chat has one constantly updated event dashboard message. Approved events are added to that dashboard as short clickable items, while full event details live in separate event card messages.

This repository is being implemented step by step. The current codebase contains the Stage 1 foundation and Stage 2 database schema.

## Project Goal

University clubs and students should be able to submit events to the bot. Submitted events go through moderation. After approval, the bot publishes each event to the correct chat dashboards based on category settings.

Instead of posting many event announcements into a group, the bot keeps one dashboard message updated.

Example dashboard item:

```text
Today

18:00 - AI Workshop, Block C, Room 301
```

In the final version, the event title will link to the detailed Telegram event message.

## Current Status

Implemented:
- Full event submission and moderation workflow
- Interactive Main Menu (My Events, Favorites, Admin Panel)
- Automatic Dashboard management in groups
- Date/Time validation (DD.MM.YYYY format)
- HTML-safe rendering for all user content
- Private Chat restrictions for startup commands

## 🚀 Quick Start for Friends

If you want to run this bot yourself:

1. **Get a Bot Token**: Message [@BotFather](https://t.me/BotFather) on Telegram to create a bot and get your `BOT_TOKEN`.
2. **Setup Environment**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and paste your `BOT_TOKEN`. Add your own Telegram ID to `ADMIN_IDS` so you can access the admin panel.
3. **Launch with Docker** (Simplest):
   ```bash
   docker compose up -d
   ```
4. **Initialize Database**:
   ```bash
   # run migrations
   docker compose exec bot alembic upgrade head
   # seed event categories
   docker compose exec bot python scripts/seed_categories.py
   ```
5. **Start Bot**: The bot will already be running in the background. Check logs with `docker compose logs -f bot`.

---

## Project Goal

Not implemented yet:

- Reminders and favorites
- Club dashboard
- Calendar commands
- Production hardening

## Planned Core Features

### Event Submission

Students or clubs will submit:

- poster or image
- title
- description
- date
- time
- location
- category
- organizer or club name
- registration link, if available

Submitted events will be saved as `pending`.

### Moderation

Moderators will be able to:

- approve events
- reject events
- edit events
- ask creators to fix submissions

Approved events become visible in matching chat dashboards.

### Event Dashboards

Each registered chat will have one dashboard message. The bot will edit that message when events are approved, updated, cancelled, expired, or when chat category settings change.

Dashboards will show:

- events today
- events tomorrow
- events this week
- event time
- short title
- location
- link to full event card

The bot will not pin messages and will not create repeated announcement spam.

### Event Detail Messages

Each approved event will have a detailed message containing:

- poster, if available
- title
- full description
- date and time
- location
- organizer
- category
- registration link, if available
- inline buttons for reminders, favorites, registration, and sharing

### Categories

Chats will be able to choose which categories they display.

Example categories:

- Computer Science
- Business
- Startups
- Engineering
- Design
- Career
- Hackathons
- Workshops
- Sport
- Volunteering
- Entertainment
- Club Events

### Reminders and Favorites

Users will be able to:

- add events to favorites
- enable reminders 1 day before an event
- enable reminders 1 hour before an event

Reminders will be sent in private messages.

### Club Dashboard

Clubs will be able to:

- create events
- view future events
- edit events
- cancel events
- replace posters
- check moderation status
- see basic statistics

## Tech Stack

- Python
- aiogram 3
- PostgreSQL
- Redis
- Docker
- Docker Compose
- Telegram Bot API
- SQLAlchemy
- Alembic

Planned for later stages:

- background jobs for reminders

## Project Structure

```text
.
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── session.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── admin_chat.py
│   │   └── start.py
│   ├── middlewares/
│   │   ├── __init__.py
│   │   └── db.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── chat.py
│   │   ├── club.py
│   │   ├── enums.py
│   │   ├── event.py
│   │   ├── favorite.py
│   │   ├── moderation.py
│   │   ├── reminder.py
│   │   └── user.py
│   └── services/
│       ├── __init__.py
│       ├── chats.py
│       ├── dashboard.py
│       └── users.py
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 20260430_0001_create_initial_tables.py
├── alembic.ini
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── README.md
├── docker-compose.yml
└── requirements.txt
```

### Important Files

- `app/main.py` - bot entrypoint and aiogram polling startup
- `app/config.py` - environment variable loader
- `app/db/base.py` - SQLAlchemy declarative base and timestamp mixin
- `app/db/session.py` - async SQLAlchemy engine and session factory
- `app/models/` - database models for the bot domain
- `app/handlers/start.py` - `/start` command handler
- `app/handlers/admin_chat.py` - group admin commands for chat registration and dashboard creation
- `app/middlewares/db.py` - per-update database session middleware
- `app/services/` - focused database and dashboard service functions
- `alembic/` - database migration environment and migration versions
- `.env.example` - example environment configuration
- `docker-compose.yml` - PostgreSQL, Redis, and bot services
- `Dockerfile` - container image for the bot
- `requirements.txt` - Python dependencies

## Requirements

- Python 3.10 or newer
- Docker Desktop
- Telegram bot token from BotFather

## Environment Variables

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Then set your bot token and admin IDs:

```env
BOT_TOKEN=1234567890:your_real_bot_token
LOG_LEVEL=INFO
APP_TIMEZONE=Asia/Almaty
DATABASE_URL=postgresql+asyncpg://events_bot:events_bot@localhost:5432/events_bot
REDIS_URL=redis://localhost:6379/0
ADMIN_IDS=[123456789]
MODERATOR_CHAT_ID=123456789
```

Never commit `.env`. It contains secrets and is ignored by Git.

## Local Development

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
```

Apply database migrations:

```bash
alembic upgrade head
```

Seed initial categories:

```bash
export PYTHONPATH=.
python scripts/seed_categories.py
```

Run the bot locally (make sure to set the PYTHONPATH so imports work correctly):

```bash
export PYTHONPATH=.
python app/main.py
```
Or run as a module:
```bash
python -m app.main
```

## Docker Usage

Build and run all services:

```bash
docker compose up --build
```

Run only PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
```

Stop services:

```bash
docker compose down
```

Stop services and remove local database/Redis volumes:

```bash
docker compose down -v
```

## Testing Stage 1

Start the bot:

```bash
python -m app.main
```

Expected terminal output includes:

```text
Bot polling started
Start polling
```

Open Telegram and send the bot:

```text
/start
```

Expected bot reply:

```text
Hello. I am the Student Events bot.
```

## Testing Stage 3

Add the bot to a test group or supergroup.

Make sure the bot has permission to:

- send messages
- edit its own messages

As a chat admin, run:

```text
/register_chat
```

Expected result:

```text
Chat registered.
```

Then run:

```text
/dashboard
```

Expected result:

- the bot sends one dashboard message to the group
- the bot replies with the saved dashboard message ID
- running `/dashboard` again edits the same dashboard message instead of creating another one
- if you delete the dashboard message and run `/dashboard` again, the bot creates a new one and saves the new message ID

## Implementation Roadmap

The project is intentionally built in small stages.

1. Basic project setup
2. Database models and migrations
3. Register chats and create dashboard message
4. Event submission flow
5. Moderation flow
6. Publishing approved events
7. Dashboard rendering
8. Reminders and favorites
9. Club dashboard
10. Calendar commands
11. Hardening and edge cases
12. Deployment

Completed stages:

- Stage 1
- Stage 2
- Stage 3
- Stage 4
- Stage 5
- Stage 6
- Stage 7

## Git Notes

Files that should be committed:

- source code
- Docker configuration
- dependency files
- `.env.example`
- README documentation

Files that should not be committed:

- `.env`
- `.venv/`
- Python cache files
- local editor or OS files

## Security Notes

- Keep the Telegram bot token private.
- If a token is accidentally committed or shared, revoke it in BotFather immediately.
- Use `.env.example` for documentation and `.env` for local secrets.
