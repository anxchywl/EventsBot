# 🎓 Student Events Telegram Bot

A refined, menu-driven Telegram bot for managing university student events without the noise. It replaces repetitive group chat announcements with a persistent, auto-updating event dashboard.

## ✨ Core Features

- **Event Dashboard**: Each registered group chat has one persistent dashboard message that the bot updates automatically.
- **Menu-Driven UI**: Clean interaction via `InlineKeyboard` menus (My Events, Favorites, Admin Panel).
- **Owner Management**: Users can view, manage, and edit their own submitted events.
- **Smart Moderation**:
  - Edits create a "draft" that requires moderator approval before merging.
  - Mandatory rejection reasons: Creators receive specific feedback if a submission is denied.
- **Security**: Strict private-chat restrictions for startup commands to prevent group chat clutter.
- **Safety**: Robust HTML escaping for all user-generated content and strict date/time validation (DD.MM.YYYY).

## 📁 Project Structure

- `app/`: Core application logic (handlers, models, services).
- `alembic/`: Database migration versions.
- `scripts/`: Utility scripts (seed categories).
- `docker-compose.yml`: Infrastructure setup.

---

## 🚀 How to Run (Quick Start)

### 📋 Prerequisites
- **Docker Desktop** installed.
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather).

### 🛠 Option 1: Running with Docker (Recommended)

1. **Setup Environment**:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and paste your `BOT_TOKEN`. Add your own Telegram ID to `ADMIN_IDS` (e.g., `[12345678]`).

2. **Start Services**:
   ```bash
   docker compose up -d
   ```

3. **Initialize Database** (First time only):
   ```bash
   # Create tables
   docker compose exec bot alembic upgrade head
   # Create event categories
   docker compose exec bot python scripts/seed_categories.py
   ```

4. **Done!**: Check logs with `docker compose logs -f bot`.

### 🐍 Option 2: Running Locally (Manual)

1. **Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Infrastructure**:
   ```bash
   docker compose up -d postgres redis
   ```
3. **Database**:
   ```bash
   alembic upgrade head
   export PYTHONPATH=.
   python scripts/seed_categories.py
   ```
4. **Run**:
   ```bash
   export PYTHONPATH=.
   python app/main.py
   ```

---

## 🎯 Bot Usage

1. **Private Chat**: Send `/start` to see the main menu.
2. **Group Chats**: 
   - Add bot to group.
   - Promote to Admin.
   - Send `/register_chat`.
   - Send `/dashboard` to create the board.
