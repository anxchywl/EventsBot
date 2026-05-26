from aiogram import Bot, F, Router
import html

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.events import (
    delete_event_completely,
    get_event_by_id,
    get_user_events,
)
from app.services.users import upsert_user_from_telegram
from app.services.telegram_links import build_event_deep_link
from app.handlers.start import get_main_menu_keyboard
from app.config import get_settings

router = Router()


# opens the current user's events list
@router.callback_query(F.data == "my_events")
async def process_my_events(callback: CallbackQuery, session: AsyncSession):
    await show_my_events(callback, session)


# returns to the current user's events list
@router.callback_query(F.data == "my_events_back")
async def process_my_events_back(callback: CallbackQuery, session: AsyncSession):
    await show_my_events(callback, session)


# renders events created by the current user
async def show_my_events(
    callback: CallbackQuery, session: AsyncSession, *, answer: bool = True
):
    user = await upsert_user_from_telegram(session, callback.from_user)
    events = await get_user_events(session, user.id)

    if not events:
        settings = get_settings()
        is_admin = user.telegram_id in settings.admin_ids

        await callback.message.edit_text(
            "📅 **Your Events**\n\n"
            "You haven't created any events yet.\n\n"
            "Use the menu below to create one or explore other options.",
            reply_markup=get_main_menu_keyboard(is_admin),
            parse_mode="Markdown",
        )
        if answer:
            await callback.answer()
        return

    builder = InlineKeyboardBuilder()

    # show status and date on each event button
    for event in events:
        status_emoji = {
            "approved": "✅",
            "pending": "⏳",
            "rejected": "❌",
            "needs_changes": "📝",
            "cancelled": "🚫",
        }
        emoji = status_emoji.get(event.status, "❓")
        date_str = event.event_date.strftime("%b %d")

        btn_text = f"{emoji} {date_str} - {event.title}"
        builder.button(text=btn_text, callback_data=f"manage_event_{event.id}")

    builder.adjust(1)
    builder.button(text="🔙 Back to Menu", callback_data="start_menu")

    text = "📅 <b>Your Events</b>\n\nSelect an event to manage:"

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    if answer:
        await callback.answer()


# shows management actions for one user event
@router.callback_query(F.data.startswith("manage_event_"))
async def process_manage_event(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split("_")[2])
    event = await get_event_by_id(session, event_id)

    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    # escape user content before rendering html
    safe_title = html.escape(event.title)
    safe_location = html.escape(event.location)
    safe_cat = html.escape(event.category.name)
    safe_desc = html.escape(event.description)

    text = (
        f"🌟 <b>{safe_title}</b>\n\n"
        f"📅 Date: {event.event_date}\n"
        f"⏰ Time: {event.event_time}\n"
        f"📍 Location: {safe_location}\n"
        f"🏷 Category: {safe_cat}\n"
        f"🚦 Status: <b>{event.status.upper()}</b>\n\n"
        f"📝 Description:\n{safe_desc}\n"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Edit", callback_data=f"edit_event_{event.id}")
    builder.button(text="🗑 Delete", callback_data=f"delete_event_{event.id}")
    builder.button(text="🔙 Back to My Events", callback_data="my_events_back")
    builder.adjust(2, 1)

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )


# forwards edit requests to the edit flow
@router.callback_query(F.data.startswith("edit_event_"))
async def process_edit_event(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    from app.handlers.event_edit import start_edit_event

    await start_edit_event(callback, state, session)


# asks the user to confirm event deletion
@router.callback_query(F.data.startswith("delete_event_"))
async def process_delete_event(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[2])

    builder = InlineKeyboardBuilder()
    builder.button(text="❗ Yes, Delete", callback_data=f"confirm_delete_{event_id}")
    builder.button(text="🔙 Cancel", callback_data=f"manage_event_{event_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        "⚠️ **Are you sure?**\n\nThis will permanently delete the event and all associated messages/reminders. This action cannot be undone.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


# deletes the event after confirmation
@router.callback_query(F.data.startswith("confirm_delete_"))
async def process_confirm_delete(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
):
    event_id = int(callback.data.split("_")[2])

    # remove database rows and telegram messages
    success = await delete_event_completely(session, bot, event_id)
    if success:
        await session.commit()
        await callback.answer("✅ Event deleted successfully.", show_alert=True)
        await show_my_events(callback, session, answer=False)
    else:
        await callback.answer(
            "❌ Error deleting event or event not found.", show_alert=True
        )


# shows favorite events from the main menu
@router.callback_query(F.data == "menu_favorites")
async def process_menu_favorites(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
):
    from app.services.reminders import get_user_favorites

    user = await upsert_user_from_telegram(session, callback.from_user)
    favorites = await get_user_favorites(session, user)

    if not favorites:
        await callback.answer("You have no favorite events yet.", show_alert=True)
        return

    lines = ["⭐ **Your Favorite Events**\n"]
    bot_user = await bot.get_me()
    # render favorites as event-page links when possible
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
        date_str = event.event_date.strftime("%b %d")
        lines.append(f"• {date_str} — {title}")

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Back to Menu", callback_data="start_menu")

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


# answers unfinished menu items
@router.callback_query(F.data == "menu_calendar")
async def process_menu_coming_soon(callback: CallbackQuery):
    await callback.answer("This feature is coming soon!", show_alert=True)
