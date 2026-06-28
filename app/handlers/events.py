from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
import html
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReminderType
from app.services.events import get_event_by_id
from app.services.rate_limit import check_bot_rate_limit
from app.services.reminders import (
    get_user_favorites,
    schedule_reminder,
    toggle_favorite,
)
from app.services.users import upsert_user_from_telegram
from app.services.telegram_links import build_event_deep_link

router = Router()


# toggles the current event as a favorite
# process favorite
@router.callback_query(F.data.startswith("fav_"))
async def process_favorite(callback: CallbackQuery, session: AsyncSession):
    if not await check_bot_rate_limit(callback.from_user.id, "bot_fav", 30, 60):
        await callback.answer("Too many requests. Try again later.")
        return
    event_id = int(callback.data.split("_")[1])
    user = await upsert_user_from_telegram(session, callback.from_user)

    added = await toggle_favorite(session, user, event_id)
    await session.commit()

    if added:
        await callback.answer("⭐ Added to favorites!")
    else:
        await callback.answer("Removed from favorites.")


# shows reminder timing choices
# process remind options
@router.callback_query(F.data.startswith("remind_opt_"))
async def process_remind_options(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[2])

    builder = InlineKeyboardBuilder()
    builder.button(text="1 Day Before", callback_data=f"remind_set_day_{event_id}")
    builder.button(text="1 Hour Before", callback_data=f"remind_set_hour_{event_id}")
    builder.button(text="Cancel", callback_data="remind_cancel")
    builder.adjust(1)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


# cancels reminder setup
# process remind cancel
@router.callback_query(F.data == "remind_cancel")
async def process_remind_cancel(callback: CallbackQuery, session: AsyncSession):
    await callback.answer("Cancelled reminder setup.")


# saves the selected reminder timing
# process remind set
@router.callback_query(F.data.startswith("remind_set_"))
async def process_remind_set(callback: CallbackQuery, session: AsyncSession):
    if not await check_bot_rate_limit(callback.from_user.id, "bot_remind", 20, 3600):
        await callback.answer("Too many requests. Try again later.")
        return
    parts = callback.data.split("_")
    time_opt = parts[2]
    event_id = int(parts[3])

    user = await upsert_user_from_telegram(session, callback.from_user)
    event = await get_event_by_id(session, event_id)

    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    # map the callback option to the reminder type
    r_type = ReminderType.ONE_DAY if time_opt == "day" else ReminderType.ONE_HOUR
    msg = await schedule_reminder(session, user, event, r_type)
    await session.commit()

    await callback.answer(msg, show_alert=True)


# lists favorite events in private chat
# cmd favorites
@router.message(Command("favorites"))
async def cmd_favorites(message: Message, session: AsyncSession, bot: Bot):
    user = await upsert_user_from_telegram(session, message.from_user)
    favorites = await get_user_favorites(session, user)

    if not favorites:
        await message.answer("You have no favorite events yet.")
        return

    lines = ["⭐ <b>Your Favorite Events</b>\n"]
    bot_user = await bot.get_me()
    # link each favorite to its private event page
    for event in favorites:
        detail_link = build_event_deep_link(
            bot_username=bot_user.username,
            public_token=event.public_token,
        )

        title = (
            f'<a href="{html.escape(detail_link, quote=True)}">{html.escape(event.title)}</a>'
            if detail_link
            else html.escape(event.title)
        )
        time_str = event.event_time.strftime("%H:%M")
        date_str = event.event_date.strftime("%b %d")
        lines.append(f"• {date_str} {time_str} — {title}, {html.escape(event.location)}")

    await message.answer("\n".join(lines), parse_mode="HTML")
