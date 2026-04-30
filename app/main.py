import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings
from app.db import async_session_maker
from app.handlers import (
    admin_chat_router,
    event_submission_router,
    events_router,
    moderation_router,
    start_router,
)
from app.middlewares import DatabaseSessionMiddleware


def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def process_reminders(bot: Bot) -> None:
    from app.services.reminders import get_due_reminders, mark_reminder_sent

    while True:
        try:
            async with async_session_maker() as session:
                due_reminders = await get_due_reminders(session)
                for reminder in due_reminders:
                    try:
                        text = f"⏰ **Reminder!**\n\nYour event **{reminder.event.title}** is coming up!"
                        await bot.send_message(
                            reminder.user.telegram_id, text, parse_mode="Markdown"
                        )
                        await mark_reminder_sent(session, reminder.id)
                        await session.commit()
                    except Exception as e:
                        logging.error(f"Failed to send reminder {reminder.id}: {e}")
        except Exception as e:
            logging.error(f"Error in reminder task: {e}")

        await asyncio.sleep(60)  # check every minute


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
    dispatcher.include_router(event_submission_router)
    dispatcher.include_router(events_router)
    dispatcher.include_router(moderation_router)
    dispatcher.include_router(start_router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.getLogger(__name__).info("Bot polling started")

        # start background tasks
        reminder_task = asyncio.create_task(process_reminders(bot))

        await dispatcher.start_polling(bot)
    finally:
        reminder_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
