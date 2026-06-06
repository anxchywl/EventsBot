# Student Events Bot

A Telegram bot and Mini App for sharing university events without flooding group chats. Students can submit events, moderators approve them, and approved events appear in Telegram dashboards and the web Mini App.

## What is this?

This project was built for student communities that organize a lot of events. Instead of sending many separate event posts into group chats, the bot keeps one event dashboard message updated for each connected group.

It is mainly for students who want to find campus events, clubs that want to submit events, moderators and admins who approve events, and Telegram groups that want a cleaner event feed.

## Features

- Telegram bot built with `aiogram`
- Event submission flow in private chat
- Moderation flow for approving, rejecting, or requesting changes
- Editable event cards with poster, title, description, date, time, location, category, and registration link
- Group setup with `/register_chat`, `/categories`, and `/dashboard`
- One dashboard message per connected group
- Category filters per group
- Telegram Mini App for browsing events
- Search, filters, favorites, reminders, and event sharing in the Mini App
- NU email registration, login, verification codes, and password reset
- Ratings and comments for events
- Admin web panel for users, reviews, stats, and connected groups
- Event analytics for opens, shares, registrations, favorites, and reminders
- Background reminder sender
- PostgreSQL migrations with Alembic

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Python | Main backend language |
| aiogram 3 | Telegram bot framework |
| FastAPI | Mini App API and static web app |
| PostgreSQL | Main database |
| Redis | Runtime support/cache-related infrastructure |
| SQLAlchemy | Database models and queries |
| Alembic | Database migrations |
| Docker Compose | Local services and production-style run |
| Vanilla JS/CSS | Telegram Mini App frontend |
| Uvicorn | Runs the FastAPI web app |

## Project Structure

```text
events_bot/
├── app/
│   ├── handlers/        # Telegram bot commands, callbacks, and flows
│   ├── models/          # SQLAlchemy database models
│   ├── services/        # Business logic for events, chats, dashboards, etc.
│   ├── web/             # FastAPI Mini App backend and static frontend
│   ├── db/              # Database engine/session setup
│   ├── middlewares/     # aiogram middleware
│   ├── config.py        # Environment settings
│   └── main.py          # Bot entrypoint
├── alembic/             # Database migrations
├── scripts/             # Helper scripts, like category seeding
├── tests/               # Unit tests
├── docker-compose.yml   # Postgres, Redis, bot, and web services
├── Dockerfile           # App image
└── README.md
```

## Getting Started

### Requirements

- Python 3.12 recommended
- Docker Desktop or Docker Engine
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram user ID for admin access

### Installation

```bash
git clone https://github.com/anxchywl/events_bot
cd events_bot

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Start PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
```

Create your environment file:

```bash
cp .env.example .env
```

Apply migrations and seed default categories:

```bash
alembic upgrade head
python3 -m scripts.seed_categories
```

## Environment Variables

Example `.env`:

```env
BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ
LOG_LEVEL=INFO
APP_TIMEZONE=Asia/Almaty

DATABASE_URL=postgresql+asyncpg://events_bot:events_bot@localhost:5432/events_bot
REDIS_URL=redis://localhost:6379/0

MINIAPP_BASE_URL=http://localhost:8000
TELEGRAM_MINIAPP_SHORT_NAME=events
MINIAPP_SESSION_TTL_SECONDS=86400

ADMIN_IDS=[123456789]
MODERATOR_CHAT_ID=123456789

TELEGRAM_DELIVERY_DELAY_SECONDS=0.15
TELEGRAM_DELIVERY_MAX_RETRIES=3

EMAIL_HOST=console
EMAIL_PORT=587
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_FROM=
EMAIL_CODE_TTL_MINUTES=10
EMAIL_RESEND_COOLDOWN_SECONDS=60
```

Notes:

- `BOT_TOKEN` is required.
- `ADMIN_IDS` controls who can access admin features.
- `EMAIL_HOST=console` prints verification codes in logs instead of sending real email. This is useful for local testing.
- Telegram production Mini Apps need a public HTTPS `MINIAPP_BASE_URL`.

## Running the Project

### Development

Run the bot:

```bash
python3 -m app.main
```

Run the Mini App web server:

```bash
uvicorn app.web.main:web_app --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

Useful local command:

```bash
docker compose up -d postgres redis
alembic upgrade head
python3 -m scripts.seed_categories
```

### Production

The repo includes a Docker Compose setup for the bot and web app:

```bash
docker compose up -d --build
```

This starts:

- `postgres`
- `redis`
- `bot`
- `web` on port `8000`

## How It Works

Simple event flow:

1. A student creates an event in the Telegram bot.
2. The event is saved as `pending`.
3. A moderator reviews it.
4. If approved, the event becomes visible.
5. Group dashboards and the Mini App show the event.
6. Users can favorite it, set reminders, share it, register, and leave reviews.

```mermaid
flowchart LR
    A["Student submits event"] --> B["Event saved as pending"]
    B --> C["Moderator reviews"]
    C --> D{"Approved?"}
    D -->|Yes| E["Event is published"]
    D -->|No| F["Rejected or needs changes"]
    E --> G["Group dashboard updates"]
    E --> H["Mini App shows event"]
    H --> I["Favorites, reminders, reviews, shares"]
```

## Main Functionality

### Telegram Bot

Students use the bot to submit and manage their events. Admins use it to moderate events and manage connected group dashboards.

Common commands:

```text
/start
/submit_event
/moderate
/register_chat
/categories
/dashboard
/favorites
```

### Mini App

The Mini App is served by FastAPI from `app/web/static`. It lets users browse approved events, filter them, open detail pages, favorite events, set reminders, share links, and review events.

### Group Dashboards

Each connected Telegram group can choose categories. The bot keeps one dashboard message updated instead of posting every event as a new message.

### Admin Panel

Admins can view basic stats, users, connected groups, audit logs, and remove inappropriate reviews.

## API Endpoints

The project has a FastAPI API for the Mini App.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/auth/session` | Create Mini App session from Telegram init data |
| POST | `/api/auth/register` | Register with email/password |
| POST | `/api/auth/verify` | Verify email code |
| POST | `/api/auth/login` | Login with email/password |
| GET | `/api/auth/profile` | Get current profile |
| PUT | `/api/auth/profile/nickname` | Update nickname |
| POST | `/api/auth/forgot-password/request` | Request password reset code |
| POST | `/api/auth/forgot-password/verify` | Verify password reset code |
| POST | `/api/auth/forgot-password/reset` | Set a new password |
| GET | `/api/events` | List approved events |
| GET | `/api/events/filters` | Get filter options |
| GET | `/api/events/{public_token}` | Get event details |
| POST | `/api/events/{public_token}/register` | Record registration click |
| GET | `/api/favorites` | List favorite events |
| POST | `/api/events/{public_token}/favorite` | Add favorite |
| DELETE | `/api/events/{public_token}/favorite` | Remove favorite |
| GET | `/api/reminders` | List reminders |
| POST | `/api/events/{public_token}/reminders` | Create reminder |
| DELETE | `/api/reminders/{reminder_id}` | Delete reminder |
| POST | `/api/events/{public_token}/share` | Create Telegram share link |
| GET | `/api/events/{public_token}/reviews` | List reviews |
| POST | `/api/events/{public_token}/reviews` | Create or update review |
| DELETE | `/api/events/{public_token}/reviews` | Delete own review |
| GET | `/api/ratings/reviews/feed` | Global review feed |
| GET | `/api/admin/stats` | Admin stats |
| GET | `/api/admin/users` | Admin user list |
| GET | `/api/admin/connected-groups` | Connected group list |
| GET | `/api/admin/audit-logs` | Admin audit logs |

## Database

The main tables are:

- `users` - Telegram users, NU email accounts, roles, blocks, nicknames
- `events` - event content, dates, status, moderation data, public token
- `event_categories` - event categories used by filters and dashboards
- `chats` - connected Telegram groups/channels
- `chat_category_settings` - categories enabled per group
- `dashboard_messages` - dashboard message IDs for each group
- `event_detail_messages` - Telegram event card messages
- `favorites` - saved events per user
- `reminders` - scheduled reminder records
- `ratings` and `comments` - event reviews
- `event_analytics` - opens, shares, registrations, and other event actions
- `moderation_logs`, `audit_logs`, `user_activity_logs` - admin/moderation history
- `email_verification_codes`, `password_reset_codes` - auth codes
- `event_sync_jobs` - background event sync work

## Configuration

Things you may want to change:

- `APP_TIMEZONE` - default timezone for event dates and reminders
- `ADMIN_IDS` - Telegram users allowed to access admin tools
- `MODERATOR_CHAT_ID` - where moderation requests can be handled
- `MINIAPP_BASE_URL` - public URL for Telegram Mini App links
- `TELEGRAM_MINIAPP_SHORT_NAME` - Mini App short name from BotFather
- `EMAIL_HOST` and email settings - switch from console codes to real email
- default categories in `scripts/seed_categories.py`

## Testing

Run the unit tests:

```bash
python3 -m unittest discover tests
```

Some loose test files also exist in the project root. They are mostly small experiments or older checks.

## Contributing

Small improvements are welcome.

```bash
git checkout -b your-change
python3 -m unittest discover tests
```

Before opening a pull request, try to include:

- what changed
- how you tested it
- screenshots if the UI changed
