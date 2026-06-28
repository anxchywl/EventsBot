from __future__ import annotations

from aiogram import Bot

from app.config import get_settings


_bot_username: str | None = None
_web_bot: Bot | None = None


def get_web_bot() -> Bot:
    global _web_bot
    if _web_bot is None:
        _web_bot = Bot(token=get_settings().bot_token.get_secret_value())
    return _web_bot


async def close_web_bot() -> None:
    global _web_bot
    if _web_bot is not None:
        await _web_bot.session.close()
        _web_bot = None


# cache bot username for telegram mini app links
async def get_bot_username() -> str | None:
    global _bot_username
    if _bot_username:
        return _bot_username
    try:
        me = await get_web_bot().get_me()
        _bot_username = me.username
        return _bot_username
    except Exception:
        return None
