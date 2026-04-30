from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.enums import EventStatus
from app.services.events import get_event_by_id, get_pending_events, update_event_status
from app.services.publisher import publish_approved_event
from app.services.users import upsert_user_from_telegram
import html


router = Router()


class ModerationState(StatesGroup):
    waiting_for_rejection_reason = State()
    waiting_for_changes_reason = State()


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
        safe_title = html.escape(event.title)
        safe_name = html.escape(event.creator.first_name)
        safe_username = html.escape(event.creator.username or "none")
        safe_location = html.escape(event.location)
        safe_desc = html.escape(event.description)

        text = (
            f"🔔 <b>Pending Event #{event.id}</b>\n\n"
            f"<b>Title:</b> {safe_title}\n"
            f"<b>User:</b> {safe_name} (@{safe_username})\n"
            f"<b>Category:</b> {event.category.name}\n"
            f"<b>Date:</b> {event.event_date} at {event.event_time}\n"
            f"<b>Location:</b> {safe_location}\n\n"
            f"<b>Description:</b>\n{safe_desc}"
        )

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

    target_event = event
    is_update = event.parent_event_id is not None

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

    await session.commit()

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

    # trigger publishing to all enabled chats and update their dashboards
    await publish_approved_event(session, bot, target_event)

    await callback.answer("Approved and published.")


@router.callback_query(F.data.startswith("mod_reject_"))
async def process_reject_button(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split("_")[2])
    await state.update_data(mod_event_id=event_id)
    await state.set_state(ModerationState.waiting_for_rejection_reason)
    await callback.message.answer("Please send the **reason for rejection**:")
    await callback.answer()


@router.callback_query(F.data.startswith("mod_changes_"))
async def process_changes_button(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split("_")[2])
    await state.update_data(mod_event_id=event_id)
    await state.set_state(ModerationState.waiting_for_changes_reason)
    await callback.message.answer("Please explain what **changes are needed**:")
    await callback.answer()


@router.message(ModerationState.waiting_for_rejection_reason, F.text)
async def process_rejection_reason(
    message: Message, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    event_id = data["mod_event_id"]
    reason = message.text

    moderator = await upsert_user_from_telegram(session, message.from_user)
    event = await update_event_status(
        session, event_id, EventStatus.REJECTED, moderator, comment=reason
    )

    if not event:
        await message.answer("Event not found.")
        await state.clear()
        return

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


@router.message(ModerationState.waiting_for_changes_reason, F.text)
async def process_changes_reason(
    message: Message, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    event_id = data["mod_event_id"]
    reason = message.text

    moderator = await upsert_user_from_telegram(session, message.from_user)
    event = await update_event_status(
        session, event_id, EventStatus.NEEDS_CHANGES, moderator, comment=reason
    )

    if not event:
        await message.answer("Event not found.")
        await state.clear()
        return

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
