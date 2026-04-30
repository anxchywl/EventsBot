from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReminderType
from app.services.events import get_event_by_id
from app.services.reminders import (
    get_user_favorites,
    schedule_reminder,
    toggle_favorite,
)
from app.services.users import upsert_user_from_telegram

router = Router()


@router.callback_query(F.data.startswith("fav_"))
async def process_favorite(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split("_")[1])
    user = await upsert_user_from_telegram(session, callback.from_user)

    added = await toggle_favorite(session, user, event_id)
    await session.commit()

    if added:
        await callback.answer("⭐ Added to favorites!")
    else:
        await callback.answer("Removed from favorites.")


@router.callback_query(F.data.startswith("remind_opt_"))
async def process_remind_options(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[2])

    builder = InlineKeyboardBuilder()
    builder.button(text="1 Day Before", callback_data=f"remind_set_day_{event_id}")
    builder.button(text="1 Hour Before", callback_data=f"remind_set_hour_{event_id}")
    builder.button(text="Cancel", callback_data="remind_cancel")
    builder.adjust(2, 1)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "remind_cancel")
async def process_remind_cancel(callback: CallbackQuery, session: AsyncSession):
    # to reset the keyboard, we just call the original keyboard generator
    # we need the event to generate it. if we don't have event_id in the data,
    # it's simpler to just delete the "remind me" menu and leave it alone,
    # but we can't easily reconstruct the whole keyboard without knowing the event.
    # a quick hack is just to remove the inline keyboard entirely or let the user ignore it.
    await callback.answer("Cancelled reminder setup.")


@router.callback_query(F.data.startswith("remind_set_"))
async def process_remind_set(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split("_")
    time_opt = parts[2]
    event_id = int(parts[3])

    user = await upsert_user_from_telegram(session, callback.from_user)
    event = await get_event_by_id(session, event_id)

    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    r_type = ReminderType.ONE_DAY if time_opt == "day" else ReminderType.ONE_HOUR
    msg = await schedule_reminder(session, user, event, r_type)
    await session.commit()

    await callback.answer(msg, show_alert=True)

    # we should ideally reset the keyboard back to normal, but for mvp we can just leave it or edit it slightly.
    # since we don't have the original publisher keyboard easily without regenerating it,
    # let's just leave the keyboard as is (the user can press it again if they want another reminder).


@router.message(Command("favorites"))
async def cmd_favorites(message: Message, session: AsyncSession):
    user = await upsert_user_from_telegram(session, message.from_user)
    favorites = await get_user_favorites(session, user)

    if not favorites:
        await message.answer("You have no favorite events yet.")
        return

    lines = ["⭐ **Your Favorite Events**\n"]
    for event in favorites:
        detail_link = None
        if event.detail_messages:
            detail_link = event.detail_messages[0].message_link

        title = (
            f'<a href="{detail_link}">{event.title}</a>' if detail_link else event.title
        )
        time_str = event.event_time.strftime("%H:%M")
        date_str = event.event_date.strftime("%b %d")
        lines.append(f"• {date_str} {time_str} — {title}, {event.location}")

    await message.answer("\n".join(lines), parse_mode="HTML")
