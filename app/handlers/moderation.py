import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.enums import EventStatus
from app.services.event_cards import escape_and_fit_description
from app.services.events import get_event_by_id, get_pending_events, update_event_status
from app.services.event_sync import (
    acquire_event_lock,
    capture_event_snapshot,
    enqueue_event_sync,
)
from app.services.users import upsert_user_from_telegram

logger = logging.getLogger(__name__)
router = Router()


# tracks moderation reason input states
class ModerationState(StatesGroup):
    waiting_for_rejection_reason = State()
    waiting_for_changes_reason = State()


# builds moderation action buttons
def get_moderation_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="Approve", callback_data=f"mod_approve_{event_id}")
    builder.button(text="Reject", callback_data=f"mod_reject_{event_id}")
    builder.button(text="Needs Changes", callback_data=f"mod_changes_{event_id}")
    builder.adjust(1)
    return builder.as_markup()


# sends pending events to moderators
@router.message(Command("moderate"))
async def cmd_moderate(message: Message, session: AsyncSession):
    settings = get_settings()
    # allow admins and the configured moderator chat
    if message.from_user.id not in settings.admin_ids:
        # check if it's the moderator chat
        if message.chat.id != settings.moderator_chat_id:
            return

    pending_events = await get_pending_events(session)
    if not pending_events:
        await message.answer("No pending events to moderate.")
        return

    # render each pending event as a moderation card
    for event in pending_events:
        safe_title = html.escape(event.title)
        safe_name = html.escape(event.creator.first_name)
        safe_username = html.escape(event.creator.username or "none")
        safe_location = html.escape(event.location)
        date_str = event.event_date.strftime("%d.%m.%Y")
        time_str = event.event_time.strftime("%H:%M")

        def render_text(safe_desc: str) -> str:
            return (
                f"🔔 <b>Pending Event #{event.id}</b>\n\n"
                f"<b>Title:</b> {safe_title}\n"
                f"<b>User:</b> {safe_name} (@{safe_username})\n"
                f"<b>Category:</b> {event.category.name}\n"
                f"<b>Date:</b> {date_str} at {time_str}\n"
                f"<b>Location:</b> {safe_location}\n\n"
                f"<b>Description:</b>\n{safe_desc}"
            )

        safe_desc = escape_and_fit_description(event.description, render_text) if event.poster_file_id else html.escape(event.description)
        text = render_text(safe_desc)

        if event.poster_file_id:
            await message.answer_photo(
                event.poster_file_id,
                caption=text,
                reply_markup=get_moderation_keyboard(event.id),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                text,
                reply_markup=get_moderation_keyboard(event.id),
                parse_mode="HTML",
            )


# approves an event or update draft
@router.callback_query(F.data.startswith("mod_approve_"))
async def process_approve(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    from app.config import get_settings
    settings = get_settings()
    user_id = callback.fromuser.id if hasattr(callback, 'fromuser') else callback.from_user.id
    if user_id not in settings.admin_ids and callback.message.chat.id != settings.moderator_chat_id:
        await callback.answer("Unauthorized.", show_alert=True)
        return

    event_id = int(callback.data.split("_")[2])
    moderator = await upsert_user_from_telegram(session, callback.from_user)

    existing = await get_event_by_id(session, event_id)
    if not existing:
        await callback.answer("Event not found.", show_alert=True)
        return

    target_event_id = existing.parent_event_id or existing.id
    await acquire_event_lock(session, target_event_id)
    snapshot = await capture_event_snapshot(session, target_event_id)

    event = await update_event_status(
        session, event_id, EventStatus.APPROVED, moderator
    )
    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    target_event = event
    is_update = event.parent_event_id is not None

    # apply draft updates to the parent event
    if is_update:
        # fetch parent event
        parent = await get_event_by_id(session, event.parent_event_id)
        if parent:
            # copy fields from draft to parent
            parent.title = event.title
            parent.description = event.description
            parent.event_date = event.event_date
            parent.event_time = event.event_time
            parent.location = event.location
            parent.category_id = event.category_id
            parent.organizer_name = event.organizer_name
            parent.poster_file_id = event.poster_file_id
            parent.registration_url = event.registration_url
            parent.status = EventStatus.APPROVED.value

            target_event = parent
            # delete the draft event
            await session.delete(event)

    await enqueue_event_sync(
        session,
        event_id=target_event.id,
        operation="approved",
        snapshot=snapshot,
    )

    from app.models.audit import AuditLog
    session.add(AuditLog(
        actor_user_id=moderator.id,
        action="approve_event",
        target_type="event",
        target_id=str(target_event.id),
        metadata_json={"is_update": is_update, "original_event_id": event_id}
    ))

    # commit the status change first — publishing errors must not roll this back
    await session.commit()

    # re-load target_event cleanly after commit so relationships are fresh
    target_event = await get_event_by_id(session, target_event.id)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ {'Update' if is_update else 'Event'} #{event_id} has been approved."
    )

    # notify creator
    try:
        await bot.send_message(
            target_event.creator.telegram_id,
            f"🎉 Your {'update for' if is_update else 'event'} '{target_event.title}' has been approved and published!",
        )
    except Exception:
        pass

    await callback.answer("Approved. Sync queued.")


def _get_moderation_reason_keyboard():
    from aiogram.utils.keyboard import ReplyKeyboardBuilder
    builder = ReplyKeyboardBuilder()
    builder.button(text="Back")
    builder.button(text="Back to Menu")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


# asks for a rejection reason
@router.callback_query(F.data.startswith("mod_reject_"))
async def process_reject_button(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split("_")[2])
    await state.update_data(mod_event_id=event_id)
    await state.set_state(ModerationState.waiting_for_rejection_reason)
    await callback.message.answer(
        "Please send the **reason for rejection**:",
        reply_markup=_get_moderation_reason_keyboard(),
    )
    await callback.answer()


# asks for requested changes
@router.callback_query(F.data.startswith("mod_changes_"))
async def process_changes_button(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split("_")[2])
    await state.update_data(mod_event_id=event_id)
    await state.set_state(ModerationState.waiting_for_changes_reason)
    await callback.message.answer(
        "Please explain what **changes are needed**:",
        reply_markup=_get_moderation_reason_keyboard(),
    )
    await callback.answer()


# handles back navigation from rejection reason prompt
@router.message(ModerationState.waiting_for_rejection_reason, F.text.in_({"Back", "Back to Menu"}))
async def handle_reject_back(message: Message, state: FSMContext, session: AsyncSession):
    from aiogram.types import ReplyKeyboardRemove
    data = await state.get_data()
    event_id = data.get("mod_event_id")
    if event_id:
        event = await session.get(Event, event_id)
        if event:
            await state.clear()
            await message.answer(
                "Rejection cancelled.",
                reply_markup=get_moderation_keyboard(event.id),
            )
            return
    await state.clear()
    await message.answer("Cancelled.")


# records a rejection reason
@router.message(ModerationState.waiting_for_rejection_reason, F.text)
async def process_rejection_reason(
    message: Message, state: FSMContext, session: AsyncSession
):
    from app.config import get_settings
    settings = get_settings()
    user_id = message.from_user.id
    if user_id not in settings.admin_ids and message.chat.id != settings.moderator_chat_id:
        return

    data = await state.get_data()
    event_id = data["mod_event_id"]
    reason = message.text

    if len(reason) > 1000:
        await message.answer("Reason is too long. Please keep it under 1000 characters.")
        return

    # mark the event as rejected with the moderator comment
    moderator = await upsert_user_from_telegram(session, message.from_user)
    await acquire_event_lock(session, event_id)
    snapshot = await capture_event_snapshot(session, event_id)
    event = await update_event_status(
        session, event_id, EventStatus.REJECTED, moderator, comment=reason
    )

    if not event:
        await message.answer("Event not found.")
        await state.clear()
        return

    is_update = event.parent_event_id is not None
    parent = None
    if is_update:
        parent = await get_event_by_id(session, event.parent_event_id)

    if is_update and parent:
        # Delete the draft event row so only the parent event remains APPROVED
        await session.delete(event)
        await enqueue_event_sync(
            session,
            event_id=event_id,
            operation="rejected",
            snapshot=snapshot,
        )
        await session.commit()
        await message.answer(
            f"❌ Update request for Event #{parent.id} has been rejected with reason: {reason}"
        )

        # notify creator
        try:
            await message.bot.send_message(
                parent.creator.telegram_id,
                f"❌ **The update request for your event '{parent.title}' has been rejected.**\n\n**Reason:** {reason}",
                parse_mode="Markdown",
            )
        except Exception:
            pass
    else:
        await enqueue_event_sync(
            session,
            event_id=event_id,
            operation="rejected",
            snapshot=snapshot,
        )
        from app.models.audit import AuditLog
        session.add(AuditLog(
            actor_user_id=moderator.id,
            action="reject_event",
            target_type="event",
            target_id=str(event_id),
            metadata_json={"reason": reason, "is_update": False}
        ))
        await session.commit()
        await message.answer(
            f"❌ Event #{event_id} has been rejected with reason: {reason}"
        )

        # notify creator
        try:
            await message.bot.send_message(
                event.creator.telegram_id,
                f"❌ **Your event '{event.title}' has been rejected.**\n\n**Reason:** {reason}",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    await state.clear()


# handles back navigation from changes reason prompt
@router.message(ModerationState.waiting_for_changes_reason, F.text.in_({"Back", "Back to Menu"}))
async def handle_changes_back(message: Message, state: FSMContext, session: AsyncSession):
    from aiogram.types import ReplyKeyboardRemove
    data = await state.get_data()
    event_id = data.get("mod_event_id")
    if event_id:
        event = await session.get(Event, event_id)
        if event:
            await state.clear()
            await message.answer(
                "Changes request cancelled.",
                reply_markup=get_moderation_keyboard(event.id),
            )
            return
    await state.clear()
    await message.answer("Cancelled.")


# records a changes-request reason
@router.message(ModerationState.waiting_for_changes_reason, F.text)
async def process_changes_reason(
    message: Message, state: FSMContext, session: AsyncSession
):
    from app.config import get_settings
    settings = get_settings()
    user_id = message.from_user.id
    if user_id not in settings.admin_ids and message.chat.id != settings.moderator_chat_id:
        return

    data = await state.get_data()
    event_id = data["mod_event_id"]
    reason = message.text

    if len(reason) > 1000:
        await message.answer("Reason is too long. Please keep it under 1000 characters.")
        return

    # mark the event as needing changes with the moderator comment
    moderator = await upsert_user_from_telegram(session, message.from_user)
    await acquire_event_lock(session, event_id)
    snapshot = await capture_event_snapshot(session, event_id)
    event = await update_event_status(
        session, event_id, EventStatus.NEEDS_CHANGES, moderator, comment=reason
    )

    if not event:
        await message.answer("Event not found.")
        await state.clear()
        return

    await enqueue_event_sync(
        session,
        event_id=event_id,
        operation="needs_changes",
        snapshot=snapshot,
    )
    from app.models.audit import AuditLog
    session.add(AuditLog(
        actor_user_id=moderator.id,
        action="needs_changes_event",
        target_type="event",
        target_id=str(event_id),
        metadata_json={"reason": reason}
    ))
    await session.commit()
    await message.answer(
        f"📝 Event #{event_id} marked as 'Needs Changes' with reason: {reason}"
    )

    # notify creator
    try:
        await message.bot.send_message(
            event.creator.telegram_id,
            f"📝 **Your event '{event.title}' requires changes.**\n\n**Moderator's note:** {reason}",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    await state.clear()
