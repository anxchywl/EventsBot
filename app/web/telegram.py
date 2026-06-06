from __future__ import annotations

from aiogram import Bot

from app.config import get_settings


_bot_username: str | None = None


async def get_bot_username() -> str | None:
    global _bot_username
    if _bot_username:
        return _bot_username

    bot = Bot(token=get_settings().bot_token.get_secret_value())
    try:
        me = await bot.get_me()
        _bot_username = me.username
        return _bot_username
    except Exception:
        return None
    finally:
        await bot.session.close()
