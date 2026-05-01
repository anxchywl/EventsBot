from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.enums import EventStatus
from app.models.event import Event
from app.services.events import get_pending_events
from app.services.users import upsert_user_from_telegram

router = Router(name="admin_panel")


# opens the admin panel
@router.callback_query(F.data == "admin_panel")
async def process_admin_panel(callback: CallbackQuery, session: AsyncSession):
    await show_admin_panel(callback, session, is_edit=False)


# returns to the admin panel by editing the message
@router.callback_query(F.data == "admin_panel_back")
async def process_admin_panel_back(callback: CallbackQuery, session: AsyncSession):
    await show_admin_panel(callback, session, is_edit=True)


# renders admin actions for authorized users
async def show_admin_panel(
    callback: CallbackQuery, session: AsyncSession, is_edit: bool
):
    # verify admin access before showing controls
    user = await upsert_user_from_telegram(session, callback.from_user)
    settings = get_settings()
    if user.telegram_id not in settings.admin_ids:
        await callback.answer("Access denied.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Moderation Queue", callback_data="admin_mod_queue")
    builder.button(text="✅ Active Events", callback_data="admin_active_events")
    builder.button(text="🔙 Back to Menu", callback_data="start_menu")

    builder.adjust(1)

    text = "🛠 <b>Admin Panel</b>\n\nSelect an administrative action:"

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


# lists pending events for moderation
@router.callback_query(F.data == "admin_mod_queue")
async def process_admin_mod_queue(callback: CallbackQuery, session: AsyncSession):
    pending = await get_pending_events(session)

    if not pending:
        await callback.answer("No pending events.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for event in pending:
        builder.button(
            text=f"#{event.id}: {event.title}",
            callback_data=f"admin_mod_event_{event.id}",
        )

    builder.button(text="🔙 Back", callback_data="admin_panel_back")
    builder.adjust(1)

    await callback.message.edit_text(
        "⏳ **Moderation Queue**\n\nSelect an event to moderate:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


# shows one event in the moderation panel
@router.callback_query(F.data.startswith("admin_mod_event_"))
async def process_admin_mod_event(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split("_")[3])
    event = await session.get(
        Event,
        event_id,
        options=[selectinload(Event.category), selectinload(Event.creator)],
    )

    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    # prepare a compact moderation summary
    text = (
        f"⏳ **Moderating Event #{event.id}**\n\n"
        f"**Title:** {event.title}\n"
        f"**User:** {event.creator.first_name} (@{event.creator.username})\n"
        f"**Date:** {event.event_date} {event.event_time}\n"
        f"**Description:**\n{event.description[:200]}..."
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"mod_approve_{event.id}")
    builder.button(text="❌ Reject", callback_data=f"mod_reject_{event.id}")
    builder.button(text="🔙 Back to Queue", callback_data="admin_mod_queue")
    builder.adjust(2, 1)

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="Markdown"
    )


# lists approved root events for admins
@router.callback_query(F.data == "admin_active_events")
async def process_admin_active_events(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(Event)
        .where(Event.status == EventStatus.APPROVED.value)
        .where(Event.parent_event_id.is_(None))
        .order_by(Event.event_date.desc())
    )
    active = result.scalars().all()

    # stop early when there is nothing to manage
    if not active:
        await callback.answer("No active events.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for event in active:
        builder.button(
            text=f"{event.event_date}: {event.title}",
            callback_data=f"admin_manage_event_{event.id}",
        )

    builder.button(text="🔙 Back", callback_data="admin_panel_back")
    builder.adjust(1)

    await callback.message.edit_text(
        "✅ **Active Events**\n\nSelect an event to manage:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


# shows admin controls for one active event
@router.callback_query(F.data.startswith("admin_manage_event_"))
async def process_admin_manage_event(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split("_")[3])
    event = await session.get(
        Event,
        event_id,
        options=[selectinload(Event.category), selectinload(Event.creator)],
    )

    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    text = (
        f"🛠 **Manage Event #{event.id}** (Admin)\n\n"
        f"**Title:** {event.title}\n"
        f"**Creator:** {event.creator.first_name} (@{event.creator.username})\n"
        f"**Status:** {event.status}\n"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Force Delete", callback_data=f"confirm_delete_{event.id}")
    builder.button(text="🔙 Back", callback_data="admin_active_events")
    builder.adjust(1)

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="Markdown"
    )
