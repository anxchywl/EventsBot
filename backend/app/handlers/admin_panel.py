import html
import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.handlers.moderation import ModerationState
from app.models.enums import EventStatus
from app.models.event import Event
from app.services.events import get_event_by_id, get_pending_events, update_event_status
from app.services.event_cards import escape_and_fit_description
from app.services.event_sync import (
    acquire_event_lock,
    capture_event_snapshot,
    enqueue_event_sync,
)
from app.services.users import upsert_user_from_telegram
from app.handlers.message_cleanup import delete_messages_fast

router = Router(name="admin_panel")


# get admin panel keyboard
def _get_admin_panel_keyboard(settings):
    builder = ReplyKeyboardBuilder()
    builder.button(text="Moderation Queue")
    builder.button(text="Active Events")
    builder.button(text="Back to Menu")
    builder.adjust(1)
    return builder.as_markup(
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an admin action",
    )


# get web admin inline keyboard
def _get_web_admin_inline_keyboard(settings):
    if not settings.miniapp_base_url:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Open Web Admin Panel",
        web_app=WebAppInfo(url=f"{settings.miniapp_base_url.rstrip('/')}?route=admin"),
    )
    return builder.as_markup()


# get admin moderation keyboard
def _get_admin_moderation_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Approve")
    builder.button(text="Reject")
    builder.button(text="Needs Changes")
    builder.button(text="Back to Queue")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


# is event archived
def _is_event_archived(event: Event) -> bool:
    if event.status == EventStatus.ARCHIVED.value:
        return True
    try:
        tz = ZoneInfo(event.timezone)
    except Exception:
        tz = UTC
    event_dt = datetime.combine(event.event_date, event.event_time).replace(tzinfo=tz)
    return event_dt + timedelta(hours=2) < datetime.now(tz)


# record admin panel message
async def _record_admin_panel_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    msg_ids = list(data.get("admin_msg_ids") or [])
    if message.message_id not in msg_ids:
        msg_ids.append(message.message_id)
    await state.update_data(
        admin_panel_msg_id=message.message_id, admin_msg_ids=msg_ids
    )


# record admin panel user message
async def _record_admin_panel_user_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    msg_ids = list(data.get("admin_msg_ids") or [])
    if message.message_id not in msg_ids:
        msg_ids.append(message.message_id)
    await state.update_data(
        admin_panel_user_msg_id=message.message_id, admin_msg_ids=msg_ids
    )


# record admin navigation message
async def _record_admin_navigation_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    msg_ids = list(data.get("admin_msg_ids") or [])
    if message.message_id not in msg_ids:
        msg_ids.append(message.message_id)
    await state.update_data(admin_msg_ids=msg_ids)


# cleanup admin panel messages
async def _cleanup_admin_panel_messages(
    state: FSMContext,
    bot,
    chat_id: int,
    *,
    preserve_user_message: bool = False,
) -> None:
    data = await state.get_data()
    msg_ids = data.get("admin_msg_ids") or []

    legacy_msg_id = data.get("admin_panel_msg_id")
    user_msg_id = data.get("admin_panel_user_msg_id")

    all_ids = set(msg_ids)
    if legacy_msg_id:
        all_ids.add(legacy_msg_id)
    if preserve_user_message and user_msg_id:
        all_ids.discard(user_msg_id)

    await delete_messages_fast(bot, chat_id, all_ids)

    if preserve_user_message and user_msg_id:
        await state.update_data(
            admin_panel_msg_id=None,
            admin_panel_user_msg_id=user_msg_id,
            admin_msg_ids=[user_msg_id],
        )
    else:
        await state.update_data(
            admin_panel_msg_id=None,
            admin_panel_user_msg_id=None,
            admin_msg_ids=[],
        )


# detach admin panel messages
async def _detach_admin_panel_messages(state: FSMContext) -> set[int]:
    data = await state.get_data()
    msg_ids = set(data.get("admin_msg_ids") or [])
    legacy_msg_id = data.get("admin_panel_msg_id")
    if legacy_msg_id:
        msg_ids.add(legacy_msg_id)
    await state.update_data(
        admin_panel_msg_id=None,
        admin_panel_user_msg_id=None,
        admin_msg_ids=[],
    )
    return msg_ids


# record admin temp message
async def _record_admin_temp_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    temp_ids = list(data.get("admin_temp_msg_ids", []))
    if message.message_id not in temp_ids:
        temp_ids.append(message.message_id)
    await state.update_data(admin_temp_msg_ids=temp_ids)


# cleanup admin temp messages
async def _cleanup_admin_temp_messages(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    temp_ids = data.get("admin_temp_msg_ids") or []
    await delete_messages_fast(bot, chat_id, temp_ids)
    await state.update_data(admin_temp_msg_ids=[])


# detach admin temp messages
async def _detach_admin_temp_messages(state: FSMContext) -> set[int]:
    data = await state.get_data()
    temp_ids = set(data.get("admin_temp_msg_ids") or [])
    await state.update_data(admin_temp_msg_ids=[])
    return temp_ids


# delete messages background
def _delete_messages_background(bot, chat_id: int, message_ids) -> None:
    ids = set(message_ids or [])
    if not ids:
        return
    asyncio.create_task(delete_messages_fast(bot, chat_id, ids))


# answer photo or text
async def _answer_photo_or_text(
    message: Message,
    *,
    photo_file_id: str | None,
    text: str,
    reply_markup,
):
    if not photo_file_id:
        return await message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    return await message.answer_photo(
        photo_file_id,
        caption=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


# send web admin panel link
async def _send_web_admin_panel_link(
    message: Message,
    state: FSMContext,
    settings,
) -> None:
    inline_markup = _get_web_admin_inline_keyboard(settings)
    if inline_markup is None:
        return
    sent = await message.answer("Web Admin Panel", reply_markup=inline_markup)
    await _record_admin_panel_message(state, sent)


# opens the admin panel via callback
# process admin panel
@router.callback_query(F.data == "admin_panel")
async def process_admin_panel(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    await show_admin_panel(callback.message, session, state, is_callback=True)


# opens the admin panel via message
# process admin panel message
@router.message(F.text.in_(["Admin Panel", "⚙️ Admin Panel"]), F.chat.type == "private")
async def process_admin_panel_message(
    message: Message, session: AsyncSession, state: FSMContext
):
    from app.handlers.start import cleanup_main_menu_warnings

    await cleanup_main_menu_warnings(message, state)
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await show_admin_panel(message, session, state, is_callback=False)


# returns to the admin panel by message text
# process admin panel back message
@router.message(F.text == "Back", F.chat.type == "private")
async def process_admin_panel_back_message(
    message: Message, session: AsyncSession, state: FSMContext
):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    try:
        await message.delete()
    except Exception:
        pass
    await show_admin_panel(
        message,
        session,
        state,
        is_callback=False,
        record_user_message=False,
        preserve_user_message=True,
    )


# returns to the admin panel by callback
# process admin panel back
@router.callback_query(F.data == "admin_panel_back")
async def process_admin_panel_back(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    await show_admin_panel(callback.message, session, state, is_callback=True)


# renders admin actions for authorized users
async def show_admin_panel(
    event_obj: Message | CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    is_callback: bool,
    *,
    record_user_message: bool = True,
    preserve_user_message: bool = False,
):
    is_callback = isinstance(event_obj, CallbackQuery)
    user_obj = event_obj.from_user
    msg_obj = event_obj.message if is_callback else event_obj

    # verify admin access before showing controls
    user = await upsert_user_from_telegram(session, user_obj)
    settings = get_settings()
    if user.telegram_id not in settings.admin_ids:
        if is_callback:
            await event_obj.answer("Access denied.", show_alert=True)
        else:
            await msg_obj.answer("Access denied.")
        return

    keyboard = _get_admin_panel_keyboard(settings)

    text = "Select an administrative action:"

    if is_callback:
        await _cleanup_admin_panel_messages(state, msg_obj.bot, msg_obj.chat.id)
        try:
            await msg_obj.delete()
        except Exception:
            pass
        await _send_web_admin_panel_link(msg_obj, state, settings)
        sent = await msg_obj.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await _record_admin_panel_message(state, sent)
        await event_obj.answer()
    else:
        await _cleanup_admin_panel_messages(
            state,
            msg_obj.bot,
            msg_obj.chat.id,
            preserve_user_message=preserve_user_message,
        )
        if record_user_message:
            await _record_admin_panel_user_message(state, msg_obj)
        await _send_web_admin_panel_link(msg_obj, state, settings)
        sent = await msg_obj.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await _record_admin_panel_message(state, sent)

    await state.update_data(
        admin_panel_mode=True,
        admin_mod_queue_mode=False,
        admin_active_events_mode=False,
        admin_mod_current_event_id=None,
    )


# lists pending events for moderation
# process admin mod queue
@router.callback_query(F.data == "admin_mod_queue")
async def process_admin_mod_queue(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    await show_admin_mod_queue(
        callback.message, session, state, is_callback=True, event_obj=callback
    )


# process admin mod queue message
@router.message(F.text == "Moderation Queue", F.chat.type == "private")
async def process_admin_mod_queue_message(
    message: Message, session: AsyncSession, state: FSMContext
):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await show_admin_mod_queue(message, session, state, is_callback=False)


# show admin mod queue
async def show_admin_mod_queue(
    message_obj: Message,
    session: AsyncSession,
    state: FSMContext,
    is_callback: bool,
    event_obj: CallbackQuery | None = None,
):
    from app.config import get_settings

    settings = get_settings()
    user_id = (
        message_obj.from_user.id
        if message_obj.from_user
        else (event_obj.from_user.id if event_obj else None)
    )
    chat_id = message_obj.chat.id
    if not user_id:
        return
    is_admin = user_id in settings.admin_ids
    is_mod_chat = chat_id == settings.moderator_chat_id
    if not (is_admin or is_mod_chat):
        if is_callback and event_obj:
            await event_obj.answer("Unauthorized.", show_alert=True)
        return

    pending = await get_pending_events(session)
    data = await state.get_data()
    was_in_mod_queue = data.get("admin_mod_queue_mode") is True
    is_back_navigation = bool(message_obj.text and "Back" in message_obj.text)

    if not pending:
        delete_ids: set[int] = set()
        if was_in_mod_queue or is_back_navigation:
            delete_ids |= await _detach_admin_panel_messages(state)
        else:
            delete_ids |= await _detach_admin_temp_messages(state)

        if is_callback or is_back_navigation:
            delete_ids.add(message_obj.message_id)
        else:
            await _record_admin_navigation_message(state, message_obj)

        builder = ReplyKeyboardBuilder()
        builder.button(text="Back")
        builder.button(text="Back to Menu")
        builder.adjust(1)

        sent = await message_obj.answer(
            "No pending events.",
            reply_markup=builder.as_markup(resize_keyboard=True),
        )
        await _record_admin_panel_message(state, sent)
        await state.update_data(admin_mod_queue_mode=True, admin_mod_queue_map={})
        if is_callback and event_obj:
            await event_obj.answer()
        _delete_messages_background(message_obj.bot, message_obj.chat.id, delete_ids)
        return

    event_map: dict[str, int] = {}
    keyboard = ReplyKeyboardBuilder()
    duplicate_counts: dict[str, int] = {}
    for event in pending:
        date_str = event.event_date.strftime("%d.%m.%Y")
        time_str = event.event_time.strftime("%H:%M")
        title = event.title
        if len(title) > 50:
            title = title[:50] + "…"
        base_label = f"{title} ({date_str} {time_str})"
        duplicate_counts[base_label] = duplicate_counts.get(base_label, 0) + 1
        label = base_label
        if duplicate_counts[base_label] > 1:
            label = f"{base_label} #{duplicate_counts[base_label]}"
        event_map[label] = event.id
        keyboard.button(text=label)

    keyboard.button(text="Back")
    keyboard.button(text="Back to Menu")
    keyboard.adjust(1)
    reply_markup = keyboard.as_markup(resize_keyboard=True)

    text = "Select an event to moderate:"

    # only cleanup if we're already in moderation queue mode (navigating within it)
    # don't cleanup on first entry from admin panel via callback
    should_cleanup = (was_in_mod_queue and is_callback) or is_back_navigation

    delete_ids: set[int] = set()
    if should_cleanup:
        delete_ids |= await _detach_admin_panel_messages(state)
        delete_ids.add(message_obj.message_id)
    else:
        delete_ids |= await _detach_admin_temp_messages(state)
        await _record_admin_navigation_message(state, message_obj)

    sent = await message_obj.answer(
        text, reply_markup=reply_markup, parse_mode="Markdown"
    )
    if is_callback and event_obj is not None:
        await event_obj.answer()

    await _record_admin_panel_message(state, sent)
    await state.update_data(
        admin_mod_queue_map=event_map,
        admin_mod_queue_mode=True,
        admin_mod_current_event_id=None,
    )
    _delete_messages_background(message_obj.bot, message_obj.chat.id, delete_ids)


from aiogram.filters import Filter


# filter admin mod queue event callbacks
class AdminModQueueEventFilter(Filter):
    async def __call__(
        self, message: Message, state: FSMContext
    ) -> bool | dict[str, int]:
        data = await state.get_data()
        if data.get("admin_mod_queue_mode") is True:
            event_map = data.get("admin_mod_queue_map")
            if event_map and message.text in event_map:
                return {"event_id": event_map[message.text]}
        return False


# filter admin mod action callbacks
class AdminModActionFilter(Filter):
    async def __call__(self, message: Message, state: FSMContext) -> bool:
        current_state = await state.get_state()
        if current_state in {
            ModerationState.waiting_for_rejection_reason,
            ModerationState.waiting_for_changes_reason,
        }:
            return False

        data = await state.get_data()
        return data.get("admin_mod_current_event_id") is not None and message.text in {
            "Approve",
            "Reject",
            "Needs Changes",
            "Back to Queue",
        }


# process admin mod action
@router.message(F.chat.type == "private", AdminModActionFilter())
async def process_admin_mod_action(
    message: Message, session: AsyncSession, state: FSMContext
):
    from app.config import get_settings

    settings = get_settings()
    if not message.from_user or message.from_user.id not in settings.admin_ids:
        # allow if they are acting in the moderator chat
        if message.chat.id != settings.moderator_chat_id:
            return

    data = await state.get_data()
    event_id = data.get("admin_mod_current_event_id")
    if event_id is None:
        return

    if message.text == "Back to Queue":
        await show_admin_mod_queue(message, session, state, is_callback=False)
        return

    if message.text == "Approve":
        await _admin_approve_event(message, session, state, event_id)
        return

    if message.text == "Reject":
        await state.update_data(mod_event_id=event_id, mod_back_to_event_id=event_id)
        await state.set_state(ModerationState.waiting_for_rejection_reason)
        keyboard = ReplyKeyboardBuilder()
        keyboard.button(text="Back")
        keyboard.button(text="Back to Queue")
        keyboard.adjust(2)
        await message.answer(
            "Please send the reason for rejection:",
            reply_markup=keyboard.as_markup(resize_keyboard=True),
        )
        return

    if message.text == "Needs Changes":
        await state.update_data(mod_event_id=event_id, mod_back_to_event_id=event_id)
        await state.set_state(ModerationState.waiting_for_changes_reason)
        keyboard = ReplyKeyboardBuilder()
        keyboard.button(text="Back")
        keyboard.button(text="Back to Queue")
        keyboard.adjust(2)
        await message.answer(
            "Please explain what changes are needed:",
            reply_markup=keyboard.as_markup(resize_keyboard=True),
        )
        return


# handles back navigation from rejection reason in admin panel
# handle admin reject back to queue
@router.message(ModerationState.waiting_for_rejection_reason, F.text == "Back to Queue")
async def handle_admin_reject_back_to_queue(
    message: Message, session: AsyncSession, state: FSMContext
):
    data = await state.get_data()
    event_id = data.get("mod_back_to_event_id")
    await state.clear()
    if event_id:
        await _show_admin_mod_event(
            message, session, state, event_id, is_callback=False
        )
    else:
        await show_admin_mod_queue(message, session, state, is_callback=False)


# handles back navigation from changes reason in admin panel
# handle admin changes back to queue
@router.message(ModerationState.waiting_for_changes_reason, F.text == "Back to Queue")
async def handle_admin_changes_back_to_queue(
    message: Message, session: AsyncSession, state: FSMContext
):
    data = await state.get_data()
    event_id = data.get("mod_back_to_event_id")
    await state.clear()
    if event_id:
        await _show_admin_mod_event(
            message, session, state, event_id, is_callback=False
        )
    else:
        await show_admin_mod_queue(message, session, state, is_callback=False)


# shows one event in the moderation panel
# process admin mod event
@router.callback_query(F.data.startswith("admin_mod_event_"))
async def process_admin_mod_event(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    event_id = int(callback.data.split("_")[3])
    await _show_admin_mod_event(
        callback.message, session, state, event_id, is_callback=True, event_obj=callback
    )


# process admin mod event message
@router.message(F.chat.type == "private", AdminModQueueEventFilter())
async def process_admin_mod_event_message(
    message: Message, session: AsyncSession, state: FSMContext, event_id: int
):
    await _show_admin_mod_event(message, session, state, event_id, is_callback=False)


# show admin mod event
async def _show_admin_mod_event(
    message_obj: Message,
    session: AsyncSession,
    state: FSMContext,
    event_id: int,
    is_callback: bool,
    event_obj: CallbackQuery | None = None,
):
    event = await session.get(
        Event,
        event_id,
        options=[selectinload(Event.category), selectinload(Event.creator)],
    )

    if not event:
        if is_callback and event_obj:
            await event_obj.answer("Event not found.", show_alert=True)
        else:
            await message_obj.answer("Event not found.")
        return

    safe_title = html.escape(event.title)
    safe_location = html.escape(event.location or "")
    safe_cat = html.escape(event.category.name if event.category else "")
    safe_creator = html.escape(
        f"{event.creator.first_name} (@{event.creator.username})"
    )
    safe_registration = html.escape(event.registration_url or "")

    def render_text(safe_desc: str) -> str:
        return _render_admin_moderation_event_text(
            event,
            safe_title=safe_title,
            safe_creator=safe_creator,
            safe_location=safe_location,
            safe_cat=safe_cat,
            safe_desc=safe_desc,
            safe_registration=safe_registration,
        )

    safe_desc = (
        escape_and_fit_description(event.description or "", render_text)
        if event.poster_file_id
        else html.escape(event.description or "")
    )
    text = render_text(safe_desc)

    reply_markup = _get_admin_moderation_keyboard()

    old_temp_ids = await _detach_admin_temp_messages(state)
    delete_ids = set(old_temp_ids)

    if not is_callback:
        delete_ids.add(message_obj.message_id)

    if event.poster_file_id:
        sent = await message_obj.answer_photo(
            event.poster_file_id,
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    else:
        sent = await message_obj.answer(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    if is_callback and event_obj is not None:
        await event_obj.answer()

    await _record_admin_panel_message(state, sent)
    await state.update_data(
        admin_mod_current_event_id=event.id,
        admin_mod_queue_mode=False,
    )
    _delete_messages_background(message_obj.bot, message_obj.chat.id, delete_ids)


# render admin manage event text
def _render_admin_manage_event_text(
    event: Event,
    *,
    safe_title: str,
    safe_creator: str,
    safe_location: str,
    safe_cat: str,
    safe_desc: str,
) -> str:
    date_str = event.event_date.strftime("%d.%m.%Y")
    time_str = event.event_time.strftime("%H:%M")
    return (
        f"<b>{safe_title}</b>\n\n"
        f"Creator: {safe_creator}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str}\n"
        f"Location: {safe_location}\n"
        f"Category: {safe_cat}\n"
        f"Status: {event.status.upper()}\n\n"
        f"Description:\n{safe_desc}\n"
    )


# render admin moderation event text
def _render_admin_moderation_event_text(
    event: Event,
    *,
    safe_title: str,
    safe_creator: str,
    safe_location: str,
    safe_cat: str,
    safe_desc: str,
    safe_registration: str,
) -> str:
    safe_status = html.escape(event.status.upper())
    date_str = event.event_date.strftime("%d.%m.%Y")
    time_str = event.event_time.strftime("%H:%M")
    return (
        f"<b>{safe_title}</b>\n\n"
        f"User: {safe_creator}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str}\n"
        f"Location: {safe_location}\n"
        f"Category: {safe_cat}\n"
        f"Status: {safe_status}\n"
        f"Registration: {safe_registration or 'None'}\n\n"
        f"Description:\n{safe_desc}\n"
    )


# admin approve event
async def _admin_approve_event(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    event_id: int,
) -> None:
    moderator = await upsert_user_from_telegram(session, message.from_user)
    existing = await get_event_by_id(session, event_id)
    if not existing:
        await message.answer(
            "Event not found.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    target_event_id = existing.parent_event_id or existing.id
    await acquire_event_lock(session, target_event_id)
    snapshot = await capture_event_snapshot(session, target_event_id)

    event = await update_event_status(
        session, event_id, EventStatus.APPROVED, moderator
    )
    if not event:
        await message.answer(
            "Event not found.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    target_event = event
    is_update = event.parent_event_id is not None
    if is_update:
        parent = await get_event_by_id(session, event.parent_event_id)
        if parent:
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
            await session.delete(event)

    await enqueue_event_sync(
        session,
        event_id=target_event.id,
        operation="approved",
        snapshot=snapshot,
    )
    await session.commit()
    target_event = await get_event_by_id(session, target_event.id)

    try:
        await message.bot.send_message(
            target_event.creator.telegram_id,
            f"Your event '{target_event.title}' has been approved and published!",
        )
    except Exception:
        pass

    await state.update_data(admin_mod_current_event_id=None)
    await message.answer(
        f"Event #{target_event.id} approved. Sync queued.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await show_admin_mod_queue(message, session, state, is_callback=False)


# lists approved root events for admins
# process admin active events
@router.callback_query(F.data == "admin_active_events")
async def process_admin_active_events(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    await show_admin_active_events(
        callback.message, session, state, is_callback=True, event_obj=callback
    )


# process admin active events message
@router.message(
    F.text.in_(["Active Events", "Back to Active Events"]), F.chat.type == "private"
)
async def process_admin_active_events_message(
    message: Message, session: AsyncSession, state: FSMContext
):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await show_admin_active_events(message, session, state, is_callback=False)


# show admin active events
async def show_admin_active_events(
    message_obj: Message,
    session: AsyncSession,
    state: FSMContext,
    is_callback: bool,
    event_obj: CallbackQuery | None = None,
):
    from app.config import get_settings

    settings = get_settings()
    user_id = (
        message_obj.from_user.id
        if message_obj.from_user
        else (event_obj.from_user.id if event_obj else None)
    )
    if not user_id or user_id not in settings.admin_ids:
        if is_callback and event_obj:
            await event_obj.answer("Unauthorized.", show_alert=True)
        return

    result = await session.execute(
        select(Event)
        .where(
            Event.status.in_([EventStatus.APPROVED.value, EventStatus.ARCHIVED.value])
        )
        .where(Event.parent_event_id.is_(None))
        .order_by(Event.event_date.asc(), Event.event_time.asc(), Event.id.asc())
    )
    active = result.scalars().all()

    # stop early when there is nothing to manage
    if not active:
        if is_callback and event_obj:
            await event_obj.answer("No active events.", show_alert=True)
        else:
            await _cleanup_admin_panel_messages(
                state, message_obj.bot, message_obj.chat.id
            )
            sent = await message_obj.answer("No active events.")
            await _record_admin_panel_user_message(state, message_obj)
            await _record_admin_panel_message(state, sent)
        return

    event_map: dict[str, int] = {}
    keyboard = ReplyKeyboardBuilder()
    for event in active:
        date_str = event.event_date.strftime("%d.%m.%Y")
        time_str = event.event_time.strftime("%H:%M")
        title = event.title
        if len(title) > 50:
            title = title[:50] + "…"
        if _is_event_archived(event):
            label = f"{title} (archived)"
        else:
            label = f"{title} ({date_str} {time_str})"
        if label in event_map:
            label = f"{label} ({event.id})"
        event_map[label] = event.id
        keyboard.button(text=label)

    keyboard.button(text="Back")
    keyboard.button(text="Back to Menu")
    keyboard.adjust(1)
    reply_markup = keyboard.as_markup(resize_keyboard=True)

    text = "Select an event to manage:"

    # only cleanup if we're already in active events mode (navigating within it)
    # don't cleanup on first entry from admin panel via callback
    data = await state.get_data()
    was_in_active_events = data.get("admin_active_events_mode") is True
    should_cleanup = (was_in_active_events and is_callback) or (
        message_obj.text and "Back" in message_obj.text
    )

    if should_cleanup:
        await _cleanup_admin_panel_messages(state, message_obj.bot, message_obj.chat.id)
        await delete_messages_fast(
            message_obj.bot, message_obj.chat.id, [message_obj.message_id]
        )
    else:
        await _cleanup_admin_temp_messages(state, message_obj.bot, message_obj.chat.id)
        await _record_admin_panel_user_message(state, message_obj)

    sent = await message_obj.answer(
        text, reply_markup=reply_markup, parse_mode="Markdown"
    )
    if is_callback and event_obj is not None:
        await event_obj.answer()

    await _record_admin_panel_message(state, sent)
    await state.update_data(
        admin_active_events_map=event_map, admin_active_events_mode=True
    )


# filter admin active event callbacks
class AdminActiveEventFilter(Filter):
    async def __call__(
        self, message: Message, state: FSMContext
    ) -> bool | dict[str, int]:
        data = await state.get_data()
        if data.get("admin_active_events_mode") is True:
            event_map = data.get("admin_active_events_map")
            if event_map and message.text in event_map:
                return {"event_id": event_map[message.text]}
        return False


# shows admin controls for one active event
# process admin manage event
@router.callback_query(F.data.startswith("admin_manage_event_"))
async def process_admin_manage_event(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    event_id = int(callback.data.split("_")[3])
    await _show_admin_manage_event(
        callback.message, session, state, event_id, is_callback=True, event_obj=callback
    )


# process admin manage event message
@router.message(F.chat.type == "private", AdminActiveEventFilter())
async def process_admin_manage_event_message(
    message: Message, session: AsyncSession, state: FSMContext, event_id: int
):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await _show_admin_manage_event(message, session, state, event_id, is_callback=False)


# process admin archive restore event
@router.message(F.text.in_({"Archive", "Restore"}), F.chat.type == "private")
async def process_admin_archive_restore_event(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    event_id = data.get("manage_event_id")
    if not event_id or not data.get("is_admin_edit"):
        return

    moderator = await upsert_user_from_telegram(session, message.from_user)
    status = EventStatus.ARCHIVED if message.text == "Archive" else EventStatus.APPROVED
    operation = "archived" if status == EventStatus.ARCHIVED else "restored"

    await acquire_event_lock(session, event_id)
    snapshot = await capture_event_snapshot(session, event_id)
    event = await update_event_status(session, event_id, status, moderator)
    if not event:
        await message.answer("Event not found.")
        return

    await enqueue_event_sync(
        session,
        event_id=event.id,
        operation=operation,
        snapshot=snapshot,
    )
    await session.commit()

    await message.answer(
        f"Event #{event.id} {'archived' if operation == 'archived' else 'restored'}. Sync queued.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _show_admin_manage_event(message, session, state, event.id, is_callback=False)


# show admin manage event
async def _show_admin_manage_event(
    message_obj: Message,
    session: AsyncSession,
    state: FSMContext,
    event_id: int,
    is_callback: bool,
    event_obj: CallbackQuery | None = None,
):
    event = await session.get(
        Event,
        event_id,
        options=[selectinload(Event.category), selectinload(Event.creator)],
    )

    if not event:
        if is_callback and event_obj:
            await event_obj.answer("Event not found.", show_alert=True)
        else:
            await message_obj.answer("Event not found.")
        return

    safe_title = html.escape(event.title)
    safe_location = html.escape(event.location or "")
    safe_cat = html.escape(event.category.name if event.category else "")
    safe_creator = html.escape(
        f"{event.creator.first_name} (@{event.creator.username})"
    )

    render_text = lambda safe_desc: _render_admin_manage_event_text(
        event,
        safe_title=safe_title,
        safe_creator=safe_creator,
        safe_location=safe_location,
        safe_cat=safe_cat,
        safe_desc=safe_desc,
    )
    safe_desc = (
        escape_and_fit_description(event.description or "", render_text)
        if event.poster_file_id
        else html.escape(event.description or "")
    )
    text = render_text(safe_desc)

    builder = ReplyKeyboardBuilder()
    builder.button(text="Edit")
    if event.status == EventStatus.ARCHIVED.value:
        builder.button(text="Restore")
    else:
        builder.button(text="Archive")
    builder.button(text="Delete")
    builder.button(text="Back to Active Events")
    builder.button(text="Back to Menu")
    builder.adjust(1)
    reply_markup = builder.as_markup(resize_keyboard=True)

    # only cleanup if we're already viewing an event (navigating within events)
    # don't cleanup on first entry from active events list via callback
    data = await state.get_data()
    was_viewing_event = data.get("manage_event_id") is not None

    await state.update_data(manage_event_id=event.id, is_admin_edit=True)

    if is_callback and event_obj is not None:
        if was_viewing_event:
            await _cleanup_admin_panel_messages(
                state, message_obj.bot, message_obj.chat.id
            )
            await delete_messages_fast(
                message_obj.bot, message_obj.chat.id, [message_obj.message_id]
            )
        else:
            await _cleanup_admin_temp_messages(
                state, message_obj.bot, message_obj.chat.id
            )

        if event.poster_file_id:
            sent = await message_obj.answer_photo(
                event.poster_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            sent = await message_obj.answer(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        await event_obj.answer()
    else:
        await _cleanup_admin_temp_messages(state, message_obj.bot, message_obj.chat.id)
        await _record_admin_panel_user_message(state, message_obj)

        if event.poster_file_id:
            sent = await message_obj.answer_photo(
                event.poster_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            sent = await message_obj.answer(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )

    await _record_admin_panel_message(state, sent)


# filter admin panel mode callbacks
class AdminPanelModeFilter(Filter):
    async def __call__(self, message: Message, state: FSMContext) -> bool:
        current_state = await state.get_state()
        if current_state and current_state.startswith("EventEdit:"):
            return False

        if message.text in {
            "Edit",
            "Archive",
            "Restore",
            "Delete",
            "Yes, Delete",
            "Cancel",
            "Title",
            "Description",
            "Category",
            "Date",
            "Time",
            "Location",
            "Organizer",
            "Poster",
            "Registration Link",
            "Submit Update",
            "Back to Event",
            "Back to Active Events",
            "Back to Menu",
        }:
            return False

        data = await state.get_data()
        return (
            data.get("admin_panel_mode") is True
            or data.get("admin_active_events_mode") is True
            or data.get("admin_mod_queue_mode") is True
        )


# process admin invalid input
@router.message(F.chat.type == "private", AdminPanelModeFilter())
async def process_admin_invalid_input(message: Message, state: FSMContext):
    await _record_admin_temp_message(state, message)
    sent = await message.answer(
        "Please choose an action from the panels. There is no such option as you wrote."
    )
    await _record_admin_temp_message(state, sent)
