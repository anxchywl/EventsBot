from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.enums import EventStatus
from app.services.events import get_event_by_id, get_pending_events, update_event_status
from app.services.publisher import publish_approved_event
from app.services.users import upsert_user_from_telegram

router = Router()


def get_moderation_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"mod_approve_{event_id}")
    builder.button(text="❌ Reject", callback_data=f"mod_reject_{event_id}")
    builder.button(text="📝 Needs Changes", callback_data=f"mod_changes_{event_id}")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("moderate"))
async def cmd_moderate(message: Message, session: AsyncSession):
    settings = get_settings()
    if message.from_user.id not in settings.admin_ids:
        # check if it's the moderator chat
        if message.chat.id != settings.moderator_chat_id:
            return

    pending_events = await get_pending_events(session)
    if not pending_events:
        await message.answer("No pending events to moderate.")
        return

    for event in pending_events:
        text = (
            f"🔔 **Pending Event #{event.id}**\n\n"
            f"**Title:** {event.title}\n"
            f"**User:** {event.creator.first_name} (@{event.creator.username})\n"
            f"**Category:** {event.category.name}\n"
            f"**Date:** {event.event_date} at {event.event_time}\n"
            f"**Location:** {event.location}\n\n"
            f"**Description:**\n{event.description}"
        )

        if event.poster_file_id:
            await message.answer_photo(
                event.poster_file_id,
                caption=text,
                reply_markup=get_moderation_keyboard(event.id),
                parse_mode="Markdown",
            )
        else:
            await message.answer(
                text,
                reply_markup=get_moderation_keyboard(event.id),
                parse_mode="Markdown",
            )


@router.callback_query(F.data.startswith("mod_approve_"))
async def process_approve(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    event_id = int(callback.data.split("_")[2])
    moderator = await upsert_user_from_telegram(session, callback.from_user)

    event = await update_event_status(
        session, event_id, EventStatus.APPROVED, moderator
    )
    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    await session.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Event #{event_id} ('{event.title}') has been approved."
    )

    # notify creator
    try:
        await bot.send_message(
            event.creator.telegram_id,
            f"🎉 Your event '{event.title}' has been approved and published!",
        )
    except Exception:
        pass

        # trigger publishing to all enabled chats and update their dashboards
    await publish_approved_event(session, bot, event)

    await callback.answer("Event approved and published.")


@router.callback_query(F.data.startswith("mod_reject_"))
async def process_reject(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split("_")[2])
    # for now, just reject without comment. we could add a state to ask for comment.
    moderator = await upsert_user_from_telegram(session, callback.from_user)

    event = await update_event_status(
        session, event_id, EventStatus.REJECTED, moderator
    )
    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    await session.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ Event #{event_id} has been rejected.")

    # notify creator
    try:
        from aiogram import Bot

        # (actually bot is available via callback.bot)
        await callback.bot.send_message(
            event.creator.telegram_id,
            f"❌ Your event '{event.title}' has been rejected by the moderator.",
        )
    except Exception:
        pass

    await callback.answer("Event rejected.")


@router.callback_query(F.data.startswith("mod_changes_"))
async def process_changes(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split("_")[2])
    moderator = await upsert_user_from_telegram(session, callback.from_user)

    event = await update_event_status(
        session, event_id, EventStatus.NEEDS_CHANGES, moderator
    )
    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    await session.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"📝 Event #{event_id} marked as 'Needs Changes'.")

    # notify creator
    try:
        await callback.bot.send_message(
            event.creator.telegram_id,
            f"📝 Your event '{event.title}' requires changes. Please contact the moderator for details.",
        )
    except Exception:
        pass

    await callback.answer("Marked as needs changes.")
