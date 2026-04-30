# Student Events Telegram Bot

A Telegram bot for managing university student events without spamming group chats.

The main idea is simple: each Telegram chat has one constantly updated event dashboard message. Approved events are added to that dashboard as short clickable items, while full event details live in separate event card messages.

This repository is being implemented step by step. The current codebase contains the Stage 1 foundation only.

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

- Basic Python project structure
- aiogram 3 bot startup
- `/start` command
- Environment-based configuration
- Docker Compose services for PostgreSQL and Redis
- Dockerfile for running the bot container

Not implemented yet:

- Database models and migrations
- Chat dashboard registration
- Event submission flow
- Moderation flow
- Event publishing
- Dashboard rendering
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

Planned for later stages:

- SQLAlchemy
- Alembic
- background jobs for reminders

## Project Structure

```text
.
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   └── handlers/
│       ├── __init__.py
│       └── start.py
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
- `app/handlers/start.py` - `/start` command handler
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

Then set your bot token:

```env
BOT_TOKEN=1234567890:your_real_bot_token
LOG_LEVEL=INFO
APP_TIMEZONE=Asia/Almaty
DATABASE_URL=postgresql+asyncpg://events_bot:events_bot@localhost:5432/events_bot
REDIS_URL=redis://localhost:6379/0
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

Run the bot locally:

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
