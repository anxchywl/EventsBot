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
from app.handlers.start import get_main_menu_keyboard
from app.config import get_settings

router = Router()


@router.callback_query(F.data == "my_events")
async def process_my_events(callback: CallbackQuery, session: AsyncSession):
    user = await upsert_user_from_telegram(session, callback.from_user)
    events = await get_user_events(session, user.id)

    if not events:
        await callback.answer("You haven't created any events yet.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()

    # we will show the list as inline buttons for simplicity
    for event in events:
        # short title with status
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
    # add a back button to main menu
    builder.button(text="🔙 Back to Menu", callback_data="submit_cancel")

    await callback.message.answer(
        "📅 **Your Events**\n\nSelect an event to manage:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("manage_event_"))
async def process_manage_event(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split("_")[2])
    event = await get_event_by_id(session, event_id)

    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

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
    builder.button(text="🔙 Back to My Events", callback_data="my_events")
    builder.adjust(2, 1)

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("edit_event_"))
async def process_edit_event(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    from app.handlers.event_edit import start_edit_event

    await start_edit_event(callback, state, session)


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


@router.callback_query(F.data.startswith("confirm_delete_"))
async def process_confirm_delete(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
):
    event_id = int(callback.data.split("_")[2])

    success = await delete_event_completely(session, bot, event_id)
    if success:
        await session.commit()
        await callback.answer("✅ Event deleted successfully.", show_alert=True)
        await process_my_events(callback, session)
    else:
        await callback.answer(
            "❌ Error deleting event or event not found.", show_alert=True
        )


@router.callback_query(F.data == "start_menu")
async def process_start_menu(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    await state.clear()
    user = await upsert_user_from_telegram(session, callback.from_user)
    settings = get_settings()
    is_admin = user.telegram_id in settings.admin_ids

    await callback.message.edit_text(
        "👋 **Welcome to the Student Events Bot!**\n\n"
        "I am here to help you stay updated with university life without the noise.\n\n"
        "Use the menu below to explore events or manage your own submissions.",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "menu_create")
async def process_menu_create(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    from app.handlers.event_submission import cmd_submit_event

    await cmd_submit_event(callback.message, state, session)
    await callback.answer()


@router.callback_query(F.data == "menu_favorites")
async def process_menu_favorites(callback: CallbackQuery, session: AsyncSession):
    # reuse the logic from cmd_favorites in app/handlers/events.py

    # we can't easily call cmd_favorites because it expects a message
    # so we'll just redirect to the service logic
    from app.services.reminders import get_user_favorites

    user = await upsert_user_from_telegram(session, callback.from_user)
    favorites = await get_user_favorites(session, user)

    if not favorites:
        await callback.answer("You have no favorite events yet.", show_alert=True)
        return

    lines = ["⭐ **Your Favorite Events**\n"]
    for event in favorites:
        detail_link = (
            event.detail_messages[0].message_link if event.detail_messages else None
        )
        title = (
            f'<a href="{detail_link}">{event.title}</a>' if detail_link else event.title
        )
        date_str = event.event_date.strftime("%b %d")
        lines.append(f"• {date_str} — {title}")

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Back to Menu", callback_data="submit_cancel")

    await callback.message.answer(
        "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "menu_calendar")
@router.callback_query(F.data == "menu_categories")
async def process_menu_coming_soon(callback: CallbackQuery):
    await callback.answer("This feature is coming soon!", show_alert=True)
