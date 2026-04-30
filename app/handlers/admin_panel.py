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


@router.callback_query(F.data == "admin_panel")
async def process_admin_panel(callback: CallbackQuery, session: AsyncSession):
    user = await upsert_user_from_telegram(session, callback.from_user)
    settings = get_settings()
    if user.telegram_id not in settings.admin_ids:
        await callback.answer("Access denied.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Moderation Queue", callback_data="admin_mod_queue")
    builder.button(text="✅ Active Events", callback_data="admin_active_events")
    builder.button(text="🔙 Back to Menu", callback_data="submit_cancel")
    builder.adjust(1)

    await callback.message.answer(
        "🛠 **Admin Panel**\n\nSelect an administrative action:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_mod_queue")
async def process_admin_mod_queue(callback: CallbackQuery, session: AsyncSession):
    pending = await get_pending_events(session)

    if not pending:
        await callback.answer("No pending events.", show_alert=True)
        return

    # for simplicity, we'll just show the first one or a list
    # let's show a list of buttons
    builder = InlineKeyboardBuilder()
    for event in pending:
        builder.button(
            text=f"#{event.id}: {event.title}",
            callback_data=f"admin_mod_event_{event.id}",
        )

    builder.button(text="🔙 Back", callback_data="admin_panel")
    builder.adjust(1)

    await callback.message.edit_text(
        "⏳ **Moderation Queue**\n\nSelect an event to moderate:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


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

    text = (
        f"⏳ **Moderating Event #{event.id}**\n\n"
        f"**Title:** {event.title}\n"
        f"**User:** {event.creator.first_name} (@{event.creator.username})\n"
        f"**Date:** {event.event_date} {event.event_time}\n"
        f"**Description:**\n{event.description[:200]}..."
    )

    # we reuse the mod keyboard but need a way to come back to queue
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"mod_approve_{event.id}")
    builder.button(text="❌ Reject", callback_data=f"mod_reject_{event.id}")
    builder.button(text="🔙 Back to Queue", callback_data="admin_mod_queue")
    builder.adjust(2, 1)

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin_active_events")
async def process_admin_active_events(callback: CallbackQuery, session: AsyncSession):
    # show all approved events
    result = await session.execute(
        select(Event)
        .where(Event.status == EventStatus.APPROVED.value)
        .where(Event.parent_event_id.is_(None))  # only real events, not drafts
        .order_by(Event.event_date.desc())
    )
    active = result.scalars().all()

    if not active:
        await callback.answer("No active events.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for event in active:
        builder.button(
            text=f"{event.event_date}: {event.title}",
            callback_data=f"admin_manage_event_{event.id}",
        )

    builder.button(text="🔙 Back", callback_data="admin_panel")
    builder.adjust(1)

    await callback.message.edit_text(
        "✅ **Active Events**\n\nSelect an event to manage:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


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
