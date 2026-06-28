# Student Events Bot

A Telegram bot and Mini App for student communities to share and discover campus events. Students submit events, moderators approve them, and approved events appear in Telegram group dashboards and the Mini App — without flooding chats.

Agent rules live in [AGENTS.md](./AGENTS.md).

## 1. Product Overview

Student communities organize many events. Sharing them through group chats creates noise, and interested students miss things or lose track across conversations.

This project keeps one auto-updating dashboard message per connected Telegram group. Students browse and interact with events through a Telegram Mini App. Clubs submit events through the bot. Moderators approve them from a dedicated chat.

Primary goals:

- Let students authenticate with a university email.
- Let clubs submit and manage events through the bot.
- Let moderators approve, reject, or request changes to events.
- Show approved events in Telegram group dashboards and the Mini App.
- Support favorites, reminders, reviews, and sharing in the Mini App.
- Notify users about upcoming events they care about.

## 2. Core Features

- Telegram bot built with aiogram 3.
- Event submission flow in private chat.
- Moderation queue — approve, reject, or request changes.
- Editable event cards — poster, title, description, date, time, location, category, registration link.
- One auto-updating dashboard message per connected Telegram group.
- Per-group category filters.
- Telegram Mini App — search, filters, favorites, reminders, sharing, reviews.
- NU email registration, login, verification codes, and password reset.
- Event analytics — opens, shares, registrations, favorites, and reminders.
- Admin web panel — users, reviews, stats, connected groups, and audit logs.
- Background reminder sender.
- PostgreSQL migrations with Alembic.

## 3. Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | aiogram 3 |
| API and web server | FastAPI + Uvicorn |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Cache | Redis |
| Mini App frontend | Vanilla JS and CSS |
| Runtime | Docker Compose |

## 4. Project Structure

```
events_bot/
├── app/
│   ├── handlers/        # bot commands, callbacks, and flows
│   ├── models/          # SQLAlchemy models
│   ├── services/        # business logic — events, chats, dashboards
│   ├── web/             # FastAPI backend and Mini App static frontend
│   ├── db/              # database engine and session setup
│   ├── middlewares/     # aiogram middleware
│   ├── config.py        # environment settings
│   └── main.py          # bot entrypoint
├── alembic/             # database migrations
├── scripts/             # helper scripts (category seeding)
├── tests/               # unit tests
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

## 5. How It Works

Event flow:

1. A student submits an event through the bot in private chat.
2. The event is saved as pending.
3. A moderator reviews it in the moderation chat.
4. If approved, the event is published.
5. Connected group dashboards update automatically.
6. The Mini App shows the event to all users.
7. Users can favorite it, set reminders, share it, register, and leave reviews.

```mermaid
flowchart LR
    A["Student submits event"] --> B["Saved as pending"]
    B --> C["Moderator reviews"]
    C --> D{"Decision"}
    D -->|Approved| E["Event published"]
    D -->|Rejected| F["Returned or removed"]
    E --> G["Group dashboards update"]
    E --> H["Mini App shows event"]
    H --> I["Favorites, reminders, reviews, shares"]
```

## 6. Group Dashboard Setup

1. Add the bot to your Telegram group or channel.
2. Grant it three admin permissions — **Delete Messages**, **Edit Messages**, **Pin Messages**.
3. The bot detects the permissions and displays a category chooser.
4. Select the event categories you want shown.
5. The bot generates and pins the dashboard automatically.
6. If the dashboard is ever deleted, run `/dashboard` in the group to recreate it.

## 7. Bot Commands

```
/start           open the bot and see the main menu
/submit_event    start the event submission flow
/moderate        open the moderation queue (moderators only)
/favorites       view favorited events
/dashboard       recreate the dashboard in a connected group
```

## 8. API Endpoints

The FastAPI backend serves the Mini App and exposes the following endpoints.

**Auth**

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/session` | Create session from Telegram init data |
| POST | `/api/auth/register` | Register with NU email and password |
| POST | `/api/auth/verify` | Verify email code |
| POST | `/api/auth/login` | Login with email and password |
| GET | `/api/auth/profile` | Get current user profile |
| PUT | `/api/auth/profile/nickname` | Update nickname |
| POST | `/api/auth/forgot-password/request` | Request a password reset code |
| POST | `/api/auth/forgot-password/verify` | Verify the reset code |
| POST | `/api/auth/forgot-password/reset` | Set a new password |

**Events**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/events` | List approved events |
| GET | `/api/events/filters` | Get filter options |
| GET | `/api/events/{token}` | Get event details |
| POST | `/api/events/{token}/register` | Record a registration click |
| GET | `/api/favorites` | List favorited events |
| POST | `/api/events/{token}/favorite` | Add a favorite |
| DELETE | `/api/events/{token}/favorite` | Remove a favorite |
| GET | `/api/reminders` | List reminders |
| POST | `/api/events/{token}/reminders` | Create a reminder |
| DELETE | `/api/reminders/{id}` | Delete a reminder |
| POST | `/api/events/{token}/share` | Create a Telegram share link |
| GET | `/api/events/{token}/reviews` | List reviews |
| POST | `/api/events/{token}/reviews` | Create or update a review |
| DELETE | `/api/events/{token}/reviews` | Delete own review |
| GET | `/api/ratings/reviews/feed` | Global review feed |

**Admin**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/admin/stats` | Overview stats |
| GET | `/api/admin/users` | User list |
| GET | `/api/admin/connected-groups` | Connected group list |
| GET | `/api/admin/audit-logs` | Audit log |
| GET | `/health` | Health check |

## 9. Database

| Table | Purpose |
|---|---|
| `users` | Telegram users, email accounts, roles, and blocks |
| `events` | Event content, dates, status, and moderation data |
| `event_categories` | Categories used by filters and dashboards |
| `chats` | Connected Telegram groups |
| `chat_category_settings` | Enabled categories per group |
| `dashboard_messages` | Dashboard message IDs per group |
| `event_detail_messages` | Event card message IDs |
| `favorites` | Saved events per user |
| `reminders` | Scheduled reminder records |
| `ratings` / `comments` | Event reviews |
| `event_analytics` | Opens, shares, registrations, and other event actions |
| `moderation_logs` / `audit_logs` | Admin and moderation history |
| `email_verification_codes` / `password_reset_codes` | Auth codes |
| `event_sync_jobs` | Background event sync work |

## 10. Local Development Setup

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

Automated production CI/CD is documented in [docs/deployment.md](docs/deployment.md).

## 11. Environment Variables

```env
# required
BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ

# app
LOG_LEVEL=INFO
APP_TIMEZONE=Asia/Almaty

# database
DATABASE_URL=postgresql+asyncpg://events_bot:events_bot@localhost:5432/events_bot

# redis
REDIS_URL=redis://localhost:6379/0

# mini app — must be a public HTTPS URL in production
MINIAPP_BASE_URL=http://localhost:8000
TELEGRAM_MINIAPP_SHORT_NAME=events
MINIAPP_SESSION_TTL_SECONDS=86400

# admin and moderation
ADMIN_IDS=[123456789]
MODERATOR_CHAT_ID=123456789

# delivery
TELEGRAM_DELIVERY_DELAY_SECONDS=0.15
TELEGRAM_DELIVERY_MAX_RETRIES=3

# email — set EMAIL_HOST=console to print codes in logs instead of sending real email
EMAIL_HOST=console
EMAIL_PORT=587
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_FROM=
EMAIL_CODE_TTL_MINUTES=10
EMAIL_RESEND_COOLDOWN_SECONDS=60
```

## 12. Testing

```bash
python3 -m unittest discover tests
```

## 13. Contributing

```bash
git checkout -b your-change
# make changes
python3 -m unittest discover tests
```

When opening a pull request, include what changed, how you tested it, and screenshots if the UI changed.
