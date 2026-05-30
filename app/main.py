import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError

from app.config import get_settings
from app.db import async_session_maker
from app.handlers import (
    admin_chat_router,
    event_submission_router,
    events_router,
    moderation_router,
    start_router,
    user_events_router,
    event_edit_router,
    event_pages_router,
    admin_panel_router,
    categories_router,
)
from app.middlewares import DatabaseSessionMiddleware


# configures process logging
def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# sends due event reminders in the background
async def process_reminders(bot: Bot) -> None:
    from app.services.reminders import get_due_reminders, mark_reminder_sent

    while True:
        try:
            # load and send reminders inside a short session
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
                        logging.error(f"failed to send reminder {reminder.id}: {e}")
        except Exception as e:
            logging.error(f"error in reminder task: {e}")

        await asyncio.sleep(60)  # check every minute


# periodically refreshes all active dashboards to remove expired events
async def periodic_dashboard_sweep() -> None:
    """
    runs every 5 minutes and enqueues a refresh for every chat that has
    a dashboard message. this ensures expired events are removed automatically
    even if no user action triggered a refresh.
    """
    from app.services.dashboard_bus import get_all_active_dashboard_chat_ids, get_bus

    # initial delay to let the bot settle before first sweep
    await asyncio.sleep(60)

    while True:
        try:
            async with async_session_maker() as session:
                chat_ids = await get_all_active_dashboard_chat_ids(session)
                if chat_ids:
                    get_bus().schedule_refresh(chat_ids)
                    logging.getLogger(__name__).debug(
                        "dashboard sweep enqueued %d chats", len(chat_ids)
                    )
        except Exception as exc:
            logging.error(f"error in dashboard sweep: {exc}")

        await asyncio.sleep(300)  # every 5 minutes


# starts the telegram bot and routers
async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # initialize the dashboard bus before routers so handlers can call get_bus()
    from app.services.dashboard_bus import init_bus

    bus = init_bus(bot=bot, session_factory=async_session_maker)
    bus.start()

    dispatcher = Dispatcher()
    # attach middleware and feature routers
    dispatcher.update.middleware(DatabaseSessionMiddleware(async_session_maker))
    dispatcher.include_router(admin_chat_router)
    dispatcher.include_router(event_submission_router)
    dispatcher.include_router(events_router)
    dispatcher.include_router(moderation_router)
    dispatcher.include_router(start_router)
    dispatcher.include_router(admin_panel_router)
    dispatcher.include_router(event_edit_router)
    dispatcher.include_router(user_events_router)
    dispatcher.include_router(event_pages_router)
    dispatcher.include_router(categories_router)

    reminder_task = None
    sweep_task = None
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.getLogger(__name__).info("bot polling started")

        # start background tasks
        reminder_task = asyncio.create_task(process_reminders(bot), name="reminders")
        sweep_task = asyncio.create_task(
            periodic_dashboard_sweep(), name="dashboard_sweep"
        )

        await dispatcher.start_polling(bot)
    except TelegramConflictError as exc:
        logging.getLogger(__name__).error(
            "Telegram polling conflict detected: %s. Ensure only one bot instance is running.",
            exc,
        )
    finally:
        bus.stop()
        if reminder_task:
            reminder_task.cancel()
        if sweep_task:
            sweep_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
