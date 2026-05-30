import html
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.enums import EventStatus
from app.models.event import Event
from app.services.events import get_pending_events
from app.services.users import upsert_user_from_telegram

router = Router(name="admin_panel")


def _get_admin_panel_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Moderation Queue")
    builder.button(text="Active Events")
    builder.button(text="Back to Menu")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


async def _record_admin_panel_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    msg_ids = list(data.get("admin_msg_ids") or [])
    if message.message_id not in msg_ids:
        msg_ids.append(message.message_id)
    await state.update_data(
        admin_panel_msg_id=message.message_id,
        admin_msg_ids=msg_ids
    )


async def _record_admin_panel_user_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    msg_ids = list(data.get("admin_msg_ids") or [])
    if message.message_id not in msg_ids:
        msg_ids.append(message.message_id)
    await state.update_data(
        admin_panel_user_msg_id=message.message_id,
        admin_msg_ids=msg_ids
    )


async def _cleanup_admin_panel_messages(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    msg_ids = data.get("admin_msg_ids") or []
    
    legacy_msg_id = data.get("admin_panel_msg_id")
    
    all_ids = set(msg_ids)
    if legacy_msg_id:
        all_ids.add(legacy_msg_id)
        
    for message_id in all_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
            
    await state.update_data(
        admin_panel_msg_id=None,
        admin_msg_ids=[]
    )


async def _record_admin_temp_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    temp_ids = list(data.get("admin_temp_msg_ids", []))
    if message.message_id not in temp_ids:
        temp_ids.append(message.message_id)
    await state.update_data(admin_temp_msg_ids=temp_ids)


async def _cleanup_admin_temp_messages(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    temp_ids = data.get("admin_temp_msg_ids") or []
    for msg_id in temp_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    await state.update_data(admin_temp_msg_ids=[])




# opens the admin panel via callback
@router.callback_query(F.data == "admin_panel")
async def process_admin_panel(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await show_admin_panel(callback.message, session, state, is_callback=True)


# opens the admin panel via message
@router.message(F.text.in_(["Admin Panel", "⚙️ Admin Panel"]), F.chat.type == "private")
async def process_admin_panel_message(message: Message, session: AsyncSession, state: FSMContext):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await show_admin_panel(message, session, state, is_callback=False)


# returns to the admin panel by message text
@router.message(F.text == "Back", F.chat.type == "private")
async def process_admin_panel_back_message(message: Message, session: AsyncSession, state: FSMContext):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    try:
        await message.delete()
    except Exception:
        pass
    await show_admin_panel(message, session, state, is_callback=False)


# returns to the admin panel by callback
@router.callback_query(F.data == "admin_panel_back")
async def process_admin_panel_back(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await show_admin_panel(callback.message, session, state, is_callback=True)


# renders admin actions for authorized users
async def show_admin_panel(
    event_obj: Message | CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    is_callback: bool,
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

    keyboard = _get_admin_panel_keyboard()

    text = "Select an administrative action:"

    if is_callback:
        await _cleanup_admin_panel_messages(state, msg_obj.bot, msg_obj.chat.id)
        try:
            await msg_obj.delete()
        except Exception:
            pass
        sent = await msg_obj.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await event_obj.answer()
    else:
        await _cleanup_admin_panel_messages(state, msg_obj.bot, msg_obj.chat.id)
        # record user triggering message to clean up later
        await state.update_data(admin_panel_user_msg_id=msg_obj.message_id)
        sent = await msg_obj.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await _record_admin_panel_message(state, sent)
    await state.update_data(admin_panel_mode=True)


# lists pending events for moderation
@router.callback_query(F.data == "admin_mod_queue")
async def process_admin_mod_queue(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await show_admin_mod_queue(callback.message, session, state, is_callback=True, event_obj=callback)


@router.message(F.text == "Moderation Queue", F.chat.type == "private")
async def process_admin_mod_queue_message(message: Message, session: AsyncSession, state: FSMContext):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await show_admin_mod_queue(message, session, state, is_callback=False)


async def show_admin_mod_queue(
    message_obj: Message,
    session: AsyncSession,
    state: FSMContext,
    is_callback: bool,
    event_obj: CallbackQuery | None = None,
):
    pending = await get_pending_events(session)

    if not pending:
        if is_callback and event_obj:
            await event_obj.answer("No pending events.", show_alert=True)
        else:
            await message_obj.answer("No pending events.")
        return

    event_map: dict[str, int] = {}
    keyboard = ReplyKeyboardBuilder()
    for event in pending:
        date_str = event.event_date.strftime("%B %d %Y")
        title = event.title
        if len(title) > 50:
            title = title[:50] + "…"
        label = f"{title} ({date_str})"
        if label in event_map:
            label = f"{label} ({event.id})"
        event_map[label] = event.id
        keyboard.button(text=label)

    keyboard.button(text="Back")
    keyboard.button(text="Back to Menu")
    keyboard.adjust(1)
    reply_markup = keyboard.as_markup(resize_keyboard=True)

    text = "Select an event to moderate:"

    should_cleanup = (is_callback or (message_obj.text and "Back" in message_obj.text))

    if should_cleanup:
        await _cleanup_admin_panel_messages(state, message_obj.bot, message_obj.chat.id)
        try:
            await message_obj.delete()
        except Exception:
            pass
    else:
        await _record_admin_panel_user_message(state, message_obj)

    sent = await message_obj.answer(text, reply_markup=reply_markup, parse_mode="Markdown")
    if is_callback and event_obj is not None:
        await event_obj.answer()

    await _record_admin_panel_message(state, sent)
    await state.update_data(admin_mod_queue_map=event_map, admin_mod_queue_mode=True)


from aiogram.filters import Filter

class AdminModQueueEventFilter(Filter):
    async def __call__(self, message: Message, state: FSMContext) -> bool | dict[str, int]:
        data = await state.get_data()
        if data.get("admin_mod_queue_mode") is True:
            event_map = data.get("admin_mod_queue_map")
            if event_map and message.text in event_map:
                return {"event_id": event_map[message.text]}
        return False

# shows one event in the moderation panel
@router.callback_query(F.data.startswith("admin_mod_event_"))
async def process_admin_mod_event(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    event_id = int(callback.data.split("_")[3])
    await _show_admin_mod_event(callback.message, session, state, event_id, is_callback=True, event_obj=callback)


@router.message(F.chat.type == "private", AdminModQueueEventFilter())
async def process_admin_mod_event_message(message: Message, session: AsyncSession, state: FSMContext, event_id: int):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await _show_admin_mod_event(message, session, state, event_id, is_callback=False)

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
    safe_desc = html.escape(event.description or "")
    safe_creator = html.escape(f"{event.creator.first_name} (@{event.creator.username})")

    # Beautiful premium event card format, identical to My Events but tailored for Admin Moderation
    text = (
        f"<b>{safe_title}</b>\n\n"
        f"User: {safe_creator}\n"
        f"Date: {event.event_date}\n"
        f"Time: {event.event_time}\n"
        f"Location: {safe_location}\n"
        f"Category: {safe_cat}\n"
        f"Status: {event.status.upper()}\n\n"
        f"Description:\n{safe_desc}\n"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"mod_approve_{event.id}")
    builder.button(text="❌ Reject", callback_data=f"mod_reject_{event.id}")
    builder.button(text="Back to Queue", callback_data="admin_mod_queue")
    builder.adjust(2)
    reply_markup = builder.as_markup()

    if is_callback and event_obj is not None:
        await _cleanup_admin_panel_messages(state, message_obj.bot, message_obj.chat.id)
        try:
            await message_obj.delete()
        except Exception:
            pass
        
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
        # Do NOT delete preceding messages or user's message
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


# lists approved root events for admins
@router.callback_query(F.data == "admin_active_events")
async def process_admin_active_events(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await show_admin_active_events(callback.message, session, state, is_callback=True, event_obj=callback)


@router.message(F.text.in_(["Active Events", "Back to Active Events"]), F.chat.type == "private")
async def process_admin_active_events_message(message: Message, session: AsyncSession, state: FSMContext):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await show_admin_active_events(message, session, state, is_callback=False)


async def show_admin_active_events(
    message_obj: Message,
    session: AsyncSession,
    state: FSMContext,
    is_callback: bool,
    event_obj: CallbackQuery | None = None,
):
    result = await session.execute(
        select(Event)
        .where(Event.status == EventStatus.APPROVED.value)
        .where(Event.parent_event_id.is_(None))
        .order_by(Event.event_date.desc())
    )
    active = result.scalars().all()

    # stop early when there is nothing to manage
    if not active:
        if is_callback and event_obj:
            await event_obj.answer("No active events.", show_alert=True)
        else:
            await message_obj.answer("No active events.")
        return

    event_map: dict[str, int] = {}
    keyboard = ReplyKeyboardBuilder()
    for event in active:
        date_str = event.event_date.strftime("%B %d %Y")
        title = event.title
        if len(title) > 50:
            title = title[:50] + "…"
        label = f"{title} ({date_str})"
        if label in event_map:
            label = f"{label} ({event.id})"
        event_map[label] = event.id
        keyboard.button(text=label)

    keyboard.button(text="Back")
    keyboard.button(text="Back to Menu")
    keyboard.adjust(1)
    reply_markup = keyboard.as_markup(resize_keyboard=True)

    text = "Select an event to manage:"

    should_cleanup = (is_callback or (message_obj.text and "Back" in message_obj.text))

    if should_cleanup:
        await _cleanup_admin_panel_messages(state, message_obj.bot, message_obj.chat.id)
        try:
            await message_obj.delete()
        except Exception:
            pass
    else:
        await _record_admin_panel_user_message(state, message_obj)

    sent = await message_obj.answer(text, reply_markup=reply_markup, parse_mode="Markdown")
    if is_callback and event_obj is not None:
        await event_obj.answer()

    await _record_admin_panel_message(state, sent)
    await state.update_data(admin_active_events_map=event_map, admin_active_events_mode=True)


class AdminActiveEventFilter(Filter):
    async def __call__(self, message: Message, state: FSMContext) -> bool | dict[str, int]:
        data = await state.get_data()
        if data.get("admin_active_events_mode") is True:
            event_map = data.get("admin_active_events_map")
            if event_map and message.text in event_map:
                return {"event_id": event_map[message.text]}
        return False

# shows admin controls for one active event
@router.callback_query(F.data.startswith("admin_manage_event_"))
async def process_admin_manage_event(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    event_id = int(callback.data.split("_")[3])
    await _show_admin_manage_event(callback.message, session, state, event_id, is_callback=True, event_obj=callback)


@router.message(F.chat.type == "private", AdminActiveEventFilter())
async def process_admin_manage_event_message(message: Message, session: AsyncSession, state: FSMContext, event_id: int):
    await _cleanup_admin_temp_messages(state, message.bot, message.chat.id)
    await _show_admin_manage_event(message, session, state, event_id, is_callback=False)


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
    safe_desc = html.escape(event.description or "")
    safe_creator = html.escape(f"{event.creator.first_name} (@{event.creator.username})")

    # Same style as My Events, rich layout
    text = (
        f"<b>{safe_title}</b>\n\n"
        f"Creator: {safe_creator}\n"
        f"Date: {event.event_date}\n"
        f"Time: {event.event_time}\n"
        f"Location: {safe_location}\n"
        f"Category: {safe_cat}\n"
        f"Status: {event.status.upper()}\n\n"
        f"Description:\n{safe_desc}\n"
    )

    builder = ReplyKeyboardBuilder()
    builder.button(text="Edit")
    builder.button(text="Delete")
    builder.button(text="Back to Active Events")
    builder.button(text="Back to Menu")
    builder.adjust(1)
    reply_markup = builder.as_markup(resize_keyboard=True)

    await state.update_data(
        manage_event_id=event.id,
        is_admin_edit=True
    )

    if is_callback and event_obj is not None:
        await _cleanup_admin_panel_messages(state, message_obj.bot, message_obj.chat.id)
        try:
            await message_obj.delete()
        except Exception:
            pass
        
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
        # Do NOT delete preceding messages or user's message
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


class AdminPanelModeFilter(Filter):
    async def __call__(self, message: Message, state: FSMContext) -> bool:
        data = await state.get_data()
        return (
            data.get("admin_panel_mode") is True
            or data.get("admin_active_events_mode") is True
            or data.get("admin_mod_queue_mode") is True
        )


@router.message(F.chat.type == "private", AdminPanelModeFilter())
async def process_admin_invalid_input(message: Message, state: FSMContext):
    await _record_admin_temp_message(state, message)
    sent = await message.answer("Please choose an action from the panels. There is no such option as you wrote.")
    await _record_admin_temp_message(state, sent)
