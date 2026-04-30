import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings
from app.db import async_session_maker
from app.handlers import admin_chat_router, start_router
from app.middlewares import DatabaseSessionMiddleware


def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.update.middleware(DatabaseSessionMiddleware(async_session_maker))
    dispatcher.include_router(admin_chat_router)
    dispatcher.include_router(start_router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.getLogger(__name__).info("Bot polling started")
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
