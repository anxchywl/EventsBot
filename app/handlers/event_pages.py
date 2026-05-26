from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReminderType
from app.models.event import Event
from app.services.analytics import record_event_action
from app.services.event_cards import (
    build_event_page_keyboard,
    build_event_share_url,
    format_event_card_text,
    render_private_events_list,
)
from app.services.events import (
    get_approved_upcoming_events,
    get_available_event_by_public_token,
)
from app.services.reminders import schedule_reminder
from app.services.telegram_links import build_event_deep_link
from app.services.users import upsert_user_from_telegram

router = Router(name="event_pages")

UNAVAILABLE_TEXT = "Event no longer available."


async def send_event_page_from_token(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    *,
    public_token: str,
    source: str,
) -> None:
    user = await upsert_user_from_telegram(session, message.from_user)
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
        await message.answer(UNAVAILABLE_TEXT)
        return

    await record_event_action(
        session,
        event=event,
        action="open",
        user=user,
        source=source,
        chat_id=message.chat.id,
    )

    bot_user = await bot.get_me()
    await send_event_page_message(
        message,
        event,
        bot_username=bot_user.username,
    )
    await session.commit()


async def send_event_page_message(
    message: Message,
    event: Event,
    *,
    bot_username: str | None,
) -> None:
    text = format_event_card_text(event)
    keyboard = build_event_page_keyboard(
        event,
        bot_username=bot_username,
        use_web_app=True,
    )
    if event.poster_file_id:
        await message.answer_photo(
            event.poster_file_id,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("er_"))
async def process_event_reminder_options(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    public_token = callback.data.removeprefix("er_")
    user = await upsert_user_from_telegram(session, callback.from_user)
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
        await callback.answer(UNAVAILABLE_TEXT, show_alert=True)
        return

    await record_event_action(
        session,
        event=event,
        action="reminder_click",
        user=user,
        source="event_page",
        chat_id=callback.message.chat.id if callback.message else None,
    )
    await session.commit()

    builder = InlineKeyboardBuilder()
    builder.button(text="1 Day Before", callback_data=f"ert_day_{public_token}")
    builder.button(text="1 Hour Before", callback_data=f"ert_hour_{public_token}")
    builder.button(text="Back to Event", callback_data=f"ev_{public_token}")
    builder.adjust(1)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("ert_"))
async def process_event_reminder_set(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    _, time_option, public_token = callback.data.split("_", 2)
    user = await upsert_user_from_telegram(session, callback.from_user)
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
        await callback.answer(UNAVAILABLE_TEXT, show_alert=True)
        return

    reminder_type = (
        ReminderType.ONE_DAY if time_option == "day" else ReminderType.ONE_HOUR
    )
    message = await schedule_reminder(session, user, event, reminder_type)
    await session.commit()

    await callback.answer(message, show_alert=True)


@router.callback_query(F.data.startswith("es_"))
async def process_event_share(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    public_token = callback.data.removeprefix("es_")
    user = await upsert_user_from_telegram(session, callback.from_user)
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
        await callback.answer(UNAVAILABLE_TEXT, show_alert=True)
        return

    await record_event_action(
        session,
        event=event,
        action="share_click",
        user=user,
        source="event_page",
        chat_id=callback.message.chat.id if callback.message else None,
    )

    bot_user = await bot.get_me()
    deep_link = build_event_deep_link(
        bot_username=bot_user.username,
        public_token=event.public_token,
    )
    share_url = build_event_share_url(event, bot_username=bot_user.username)

    builder = InlineKeyboardBuilder()
    if share_url:
        builder.button(text="Share via Telegram", url=share_url)

    await callback.message.answer(
        f"Share this event:\n{deep_link}",
        reply_markup=builder.as_markup() if share_url else None,
    )
    await session.commit()
    await callback.answer()


@router.callback_query(F.data == "events_back")
async def process_events_back(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    bot_user = await bot.get_me()
    events = list(await get_approved_upcoming_events(session))
    await callback.message.answer(
        render_private_events_list(events, bot_username=bot_user.username),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ev_"))
async def process_event_page_open(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    public_token = callback.data.removeprefix("ev_")
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
        await callback.answer(UNAVAILABLE_TEXT, show_alert=True)
        return

    bot_user = await bot.get_me()
    await callback.message.edit_reply_markup(
        reply_markup=build_event_page_keyboard(
            event,
            bot_username=bot_user.username,
            use_web_app=True,
        )
    )
    await callback.answer()
