from aiogram import F, Router
import html
import re

from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from urllib.parse import urlparse

from app.config import get_settings
from app.handlers.message_cleanup import delete_messages_fast
from app.models.enums import EventStatus, ModerationAction
from app.models.event import Event
from app.models.moderation import ModerationLog
from app.services.events import get_event_by_id, cleanup_previous_drafts, replace_pending_drafts_for_parent
from app.services.event_sync import (
    acquire_event_lock,
    capture_event_snapshot,
    enqueue_event_sync,
)
from app.services.users import upsert_user_from_telegram
from app.handlers.event_submission import validate_poster_image

router = Router(name="event_edit")

EDIT_DATE_PROMPT = "Event date (DD MM YYYY)"
EDIT_TIME_PROMPT = "Start time (HH MM)"
_EDIT_DATE_RE = re.compile(r"^(\d{2}) (\d{2}) (\d{4})$")
_EDIT_TIME_RE = re.compile(r"^(\d{2}) (\d{2})$")


# parse edit date
def _parse_edit_date(value: str):
    from datetime import datetime

    match = _EDIT_DATE_RE.fullmatch(value.strip())
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


# parse edit time
def _parse_edit_time(value: str):
    from datetime import datetime

    match = _EDIT_TIME_RE.fullmatch(value.strip())
    if not match:
        return None
    hour, minute = map(int, match.groups())
    if hour > 23 or minute > 59:
        return None
    return datetime(2000, 1, 1, hour, minute).time()


# tracks states for editing an existing event
class EventEdit(StatesGroup):
    choosing_field = State()
    editing_title = State()
    editing_description = State()
    editing_category = State()
    editing_date = State()
    editing_time = State()
    editing_location = State()
    editing_organizer = State()
    editing_poster = State()
    editing_registration_link = State()


# starts the edit workflow for an event
# start edit event
@router.callback_query(F.data.startswith("edit_event_"))
async def start_edit_event(
    source: CallbackQuery | Message,
    state: FSMContext,
    session: AsyncSession,
    event_id: int | None = None,
    use_reply_keyboard: bool = False,
):
    if isinstance(source, CallbackQuery):
        if event_id is None:
            event_id = int(source.data.split("_")[2])
        event = await get_event_by_id(session, event_id)
        if not event:
            await source.answer("Event not found.", show_alert=True)
            return
        message = source.message
    else:
        if event_id is None:
            await source.answer("Event not found.")
            return
        event = await get_event_by_id(session, event_id)
        if not event:
            await source.answer("Event not found.")
            return
        message = source

    if event.status not in (
        EventStatus.APPROVED.value,
        EventStatus.PENDING.value,
        EventStatus.NEEDS_CHANGES.value,
        EventStatus.REJECTED.value,
    ):
        await source.answer(
            f"Cannot edit event in '{event.status}' status.", show_alert=True
        )
        return

    from app.config import get_settings
    settings = get_settings()
    user_id = source.from_user.id
    if event.creator_user_id != user_id and user_id not in settings.admin_ids:
        await source.answer("Unauthorized.", show_alert=True)
        return

    old_data = await state.get_data()
    manage_event_msg_id = old_data.get("manage_event_msg_id")
    my_events_choose_msg_id = old_data.get("my_events_choose_msg_id")
    my_events_selection_msg_id = old_data.get("my_events_selection_msg_id")
    my_events_cmd_msg_id = old_data.get("my_events_cmd_msg_id")

    # preserve admin-specific fields
    is_admin_edit = old_data.get("is_admin_edit")
    admin_panel_msg_id = old_data.get("admin_panel_msg_id")
    admin_panel_user_msg_id = old_data.get("admin_panel_user_msg_id")
    admin_active_events_map = old_data.get("admin_active_events_map")
    admin_active_events_mode = old_data.get("admin_active_events_mode")
    admin_mod_queue_map = old_data.get("admin_mod_queue_map")
    admin_mod_queue_mode = old_data.get("admin_mod_queue_mode")
    admin_msg_ids = old_data.get("admin_msg_ids")

    await state.clear()
    await state.update_data(
        original_event_id=event.id,
        category_id=event.category_id,
        category_name=event.category.name,
        title=event.title,
        description=event.description,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.strftime("%H:%M"),
        location=event.location,
        organizer=event.organizer_name,
        poster_file_id=event.poster_file_id,
        registration_url=event.registration_url,
        edit_use_reply_keyboard=use_reply_keyboard,
        manage_event_msg_id=manage_event_msg_id,
        my_events_choose_msg_id=my_events_choose_msg_id,
        my_events_selection_msg_id=my_events_selection_msg_id,
        my_events_cmd_msg_id=my_events_cmd_msg_id,
        # preserve admin-specific fields
        is_admin_edit=is_admin_edit,
        admin_panel_msg_id=admin_panel_msg_id,
        admin_panel_user_msg_id=admin_panel_user_msg_id,
        admin_active_events_map=admin_active_events_map,
        admin_active_events_mode=admin_active_events_mode,
        admin_mod_queue_map=admin_mod_queue_map,
        admin_mod_queue_mode=admin_mod_queue_mode,
        admin_msg_ids=admin_msg_ids,
    )
    if not isinstance(source, CallbackQuery):
        await _record_edit_message(state, source)

    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(
        message,
        state,
        is_new_message=not isinstance(source, CallbackQuery),
    )
    if isinstance(source, CallbackQuery):
        await source.answer()


# shows the editable event preview and field buttons
async def show_edit_menu(
    message: Message,
    state: FSMContext,
    is_new_message: bool = True,
    use_reply_keyboard: bool = False,
):
    data = await state.get_data()

    text = "Select a field to edit, or submit the update when you're done."

    use_reply_keyboard = use_reply_keyboard or data.get("edit_use_reply_keyboard", False)
    if use_reply_keyboard:
        builder = ReplyKeyboardBuilder()
        builder.button(text="Title")
        builder.button(text="Description")
        builder.button(text="Category")
        builder.button(text="Date")
        builder.button(text="Time")
        builder.button(text="Location")
        builder.button(text="Organizer")
        builder.button(text="Poster")
        builder.button(text="Registration Link")
        builder.button(text="Submit Update")
        builder.button(text="Back to Event")
        builder.adjust(1)
        reply_markup = builder.as_markup(resize_keyboard=True)
    else:
        builder = InlineKeyboardBuilder()
        builder.button(text="Title", callback_data="edit_field_title")
        builder.button(text="Description", callback_data="edit_field_description")
        builder.button(text="Category", callback_data="edit_field_category")
        builder.button(text="Date", callback_data="edit_field_date")
        builder.button(text="Time", callback_data="edit_field_time")
        builder.button(text="Location", callback_data="edit_field_location")
        builder.button(text="Organizer", callback_data="edit_field_organizer")
        builder.button(text="Poster", callback_data="edit_field_poster")
        builder.button(text="Registration Link", callback_data="edit_field_registration_link")
        builder.button(text="Submit Update", callback_data="edit_submit")
        builder.button(text="Back to Event", callback_data="edit_cancel")
        builder.adjust(1)
        reply_markup = builder.as_markup()

    if is_new_message:
        sent = await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
        await _record_edit_message(state, sent)
    else:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        await _record_edit_message(state, message)


# routes the selected field to its edit state via callback or reply keyboard
# process edit field choice
@router.callback_query(EventEdit.choosing_field, F.data.startswith("edit_field_"))
async def process_edit_field_choice(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await _process_edit_field_choice(
        callback.data.split("_")[2],
        callback.message,
        state,
        session,
        replace_menu_message=True,
    )
    await callback.answer()


# cancel edit from any state
@router.message(F.text == "Back to Event")
async def cancel_edit_from_any_state(message: Message, state: FSMContext, session: AsyncSession):
    current_state = await state.get_state()
    if not current_state or not current_state.startswith("EventEdit"):
        return
    return await _back_to_event_from_message(message, state, session)


@router.message(StateFilter(EventEdit.choosing_field), F.text.in_([
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
]))
# process edit field choice text
async def process_edit_field_choice_text(
    message: Message, state: FSMContext, session: AsyncSession
):
    await _record_edit_message(state, message)
    text = message.text
    if text == "Submit Update":
        return await _submit_update_from_message(message, state, session)
    if text == "Back to Event":
        return await _back_to_event_from_message(message, state, session)

    field = text.lower().replace(" ", "_")
    await _process_edit_field_choice(field, message, state, session)


# fallback for invalid text in choosing_field state
# invalid choosing field edit
@router.message(StateFilter(EventEdit.choosing_field))
async def invalid_choosing_field_edit(message: Message, state: FSMContext):
    await _record_temp_edit_message(state, message)
    sent = await message.answer("Please use the panels/keyboard to select an option. There is no such option as you wrote.")
    await _record_temp_edit_message(state, sent)


# process edit field choice
async def _process_edit_field_choice(
    field: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    replace_menu_message: bool = False,
):
    states_map = {
        "title": EventEdit.editing_title,
        "description": EventEdit.editing_description,
        "category": EventEdit.editing_category,
        "date": EventEdit.editing_date,
        "time": EventEdit.editing_time,
        "location": EventEdit.editing_location,
        "organizer": EventEdit.editing_organizer,
        "poster": EventEdit.editing_poster,
        "registration_link": EventEdit.editing_registration_link,
    }

    next_state = states_map.get(field)
    if next_state:
        # delete temporary wrong inputs and warnings from the previous steps
        await _delete_temp_edit_messages(state, message.bot, message.chat.id)
        await state.set_state(next_state)
        
        if field == "category":
            from app.services.events import get_active_categories
            categories = await get_active_categories(session)
            builder = ReplyKeyboardBuilder()
            for cat in categories:
                builder.button(text=cat.name)
            builder.button(text="Back to Event")
            builder.adjust(1)

            prompt = "Please choose a new category for the event:"
            if replace_menu_message:
                await delete_messages_fast(message.bot, message.chat.id, [message.message_id])
                sent = await message.answer(
                    prompt,
                    reply_markup=builder.as_markup(resize_keyboard=True),
                )
                await _record_edit_message(state, sent)
            else:
                sent = await message.answer(
                    prompt,
                    reply_markup=builder.as_markup(resize_keyboard=True),
                )
                await _record_edit_message(state, sent)
            return

        prompt = f"Please send the new {field.replace('_', ' ')}:"
        if field == "date":
            prompt = EDIT_DATE_PROMPT
        elif field == "time":
            prompt = EDIT_TIME_PROMPT
        elif field == "registration_link":
            prompt = (
                "Please send the new registration link in full URL form (https://...)."
            )

        if replace_menu_message:
            await message.edit_text(prompt, reply_markup=None, parse_mode="Markdown")
            await _record_edit_message(state, message)
        else:
            sent = await message.answer(
                prompt,
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove(),
            )
            await _record_edit_message(state, sent)
    else:
        sent = await message.answer("Not implemented yet.")
        await _record_edit_message(state, sent)


# validates and stores text edits
@router.message(
    StateFilter(
        EventEdit.editing_title,
        EventEdit.editing_description,
        EventEdit.editing_date,
        EventEdit.editing_time,
        EventEdit.editing_location,
        EventEdit.editing_organizer,
        EventEdit.editing_registration_link,
    )
)
# process text edit
async def process_text_edit(message: Message, state: FSMContext):
    # track this answer so it can still be deleted when the user cancels
    await _record_edit_message(state, message)

    current_state = await state.get_state()
    field = current_state.split(":")[1].replace("editing_", "")

    # prepare date and time validation helpers
    from zoneinfo import ZoneInfo
    from app.config import get_settings
    from datetime import datetime, timedelta

    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    now = datetime.now(tz)

    # validate date and time fields before saving them
    if field == "date":
        val = _parse_edit_date(message.text)
        if val is None:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Invalid date. Use DD MM YYYY, for example 22 11 2026.")
            await _record_temp_edit_message(state, sent)
            return
        if val < now.date():
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Date cannot be in the past. Use DD MM YYYY.")
            await _record_temp_edit_message(state, sent)
            return
        if val > now.date() + timedelta(days=365):
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Date cannot be more than 1 year in the future.")
            await _record_temp_edit_message(state, sent)
            return
        await state.update_data(event_date=val.isoformat())
        field = "event_date"
    elif field == "time":
        val = _parse_edit_time(message.text)
        if val is None:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Invalid time. Use HH MM, for example 18 30.")
            await _record_temp_edit_message(state, sent)
            return
        data = await state.get_data()
        event_date = datetime.strptime(data["event_date"], "%Y-%m-%d").date()
        if event_date == now.date() and val < now.time():
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Time cannot be in the past for today.")
            await _record_temp_edit_message(state, sent)
            return
        await state.update_data(event_time=val.strftime("%H:%M"))
        field = "event_time"

    # validate plain text fields before saving them
    if field == "title":
        if len(message.text) > 100:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Title is too long. Max 100 characters.")
            await _record_temp_edit_message(state, sent)
            return
        await state.update_data(title=message.text)
    elif field == "description":
        if len(message.text) > 1000:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Description is too long. Max 1000 characters.")
            await _record_temp_edit_message(state, sent)
            return
        await state.update_data(description=message.text)
    elif field == "event_date":
        pass
    elif field == "event_time":
        pass
    elif field == "location":
        if len(message.text) > 100:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Location is too long. Max 100 characters.")
            await _record_temp_edit_message(state, sent)
            return
        await state.update_data(location=message.text)
    elif field == "organizer":
        if len(message.text) > 100:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Organizer name is too long. Max 100 characters.")
            await _record_temp_edit_message(state, sent)
            return
        await state.update_data(organizer=message.text)
    elif field == "registration_link":
        if not _is_valid_url(message.text) or len(message.text) > 2048:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Please send a valid URL that starts with http:// or https:// (max 2048 chars).")
            await _record_temp_edit_message(state, sent)
            return
        await state.update_data(registration_url=message.text)

    await _delete_temp_edit_messages(state, message.bot, message.chat.id)

    # return to the edit menu after each successful change without deleting intermediate edits
    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(message, state, is_new_message=True)


# validates and stores category edit
# process category edit
@router.message(StateFilter(EventEdit.editing_category))
async def process_category_edit(message: Message, state: FSMContext, session: AsyncSession):
    await _record_edit_message(state, message)

    if message.text == "Back to Event":
        return await _back_to_event_from_message(message, state, session)

    from app.services.events import get_active_categories
    categories = await get_active_categories(session)
    category = next((c for c in categories if c.name == message.text), None)

    if not category:
        await _record_temp_edit_message(state, message)
        sent = await message.answer("Category not found. Please choose from the keyboard.")
        await _record_temp_edit_message(state, sent)
        return

    await state.update_data(category_id=category.id, category_name=category.name)
    await _delete_temp_edit_messages(state, message.bot, message.chat.id)

    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(message, state, is_new_message=True)


# fallback for non-photo poster uploads
# invalid poster edit
@router.message(EventEdit.editing_poster, ~F.photo)
async def invalid_poster_edit(message: Message, state: FSMContext):
    await _record_temp_edit_message(state, message)
    sent = await message.answer("Please send a valid photo for the poster.")
    await _record_temp_edit_message(state, sent)


# stores a replacement poster
# process poster edit
@router.message(EventEdit.editing_poster, F.photo)
async def process_poster_edit(message: Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass
    await _delete_temp_edit_messages(state, message.bot, message.chat.id)
    photo_id = message.photo[-1].file_id
    if not await validate_poster_image(message, message.bot, photo_id):
        return
    await state.update_data(poster_file_id=photo_id)
    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(message, state, is_new_message=True)


# cancels the edit workflow / back to event
# cancel edit
@router.callback_query(EventEdit.choosing_field, F.data == "edit_cancel")
async def cancel_edit(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    event_id = data.get("original_event_id")
    if event_id:
        event = await get_event_by_id(session, event_id)
        if event:
            await _delete_edit_messages(state, callback.bot, callback.message.chat.id)
            await state.set_state(None)
            keys_to_remove = [
                "original_event_id", "category_id", "category_name", "title",
                "description", "event_date", "event_time", "location",
                "organizer", "poster_file_id", "registration_url",
                "edit_use_reply_keyboard", "edit_bot_message_ids",
                "edit_temp_message_ids"
            ]
            for key in keys_to_remove:
                data.pop(key, None)
            data["manage_event_id"] = event_id
            await state.set_data(data)
            
            # edit the message back to the clean event card details
            import html
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            safe_title = html.escape(event.title)
            safe_location = html.escape(event.location)
            safe_cat = html.escape(event.category.name)
            safe_desc = html.escape(event.description)

            if data.get("is_admin_edit"):
                # clean up edit message and resend the admin panel manage event view
                await callback.message.delete()
                from app.handlers.admin_panel import _show_admin_manage_event
                await _show_admin_manage_event(callback.message, session, state, event.id, is_callback=False)
                await callback.answer()
                return

            date_str = event.event_date.strftime("%d.%m.%Y")
            time_str = event.event_time.strftime("%H:%M")
            text = (
                f"<b>{safe_title}</b>\n\n"
                f"Date: {date_str}\n"
                f"Time: {time_str}\n"
                f"Location: {safe_location}\n"
                f"Category: {safe_cat}\n"
                f"Status: <b>{event.status.upper()}</b>\n\n"
                f"Description:\n{safe_desc}\n"
            )

            builder = InlineKeyboardBuilder()
            builder.button(text="Edit", callback_data=f"edit_event_{event.id}")
            builder.button(text="Delete", callback_data=f"delete_event_{event.id}")
            builder.button(text="Back to My Events", callback_data="my_events_back")
            builder.adjust(1)

            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await callback.answer()
            return

    await _delete_edit_messages(state, callback.bot, callback.message.chat.id)
    await state.set_state(None)
    await callback.message.edit_text("Edit cancelled.")
    await callback.answer()


# record edit message
async def _record_edit_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    message_ids = list(data.get("edit_bot_message_ids", []))
    if message.message_id not in message_ids:
        message_ids.append(message.message_id)
    await state.update_data(edit_bot_message_ids=message_ids)


# record temp edit message
async def _record_temp_edit_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    
    # record in general bot message list
    message_ids = list(data.get("edit_bot_message_ids", []))
    if message.message_id not in message_ids:
        message_ids.append(message.message_id)
        
    # record in temp/wrong messages list
    temp_ids = list(data.get("edit_temp_message_ids", []))
    if message.message_id not in temp_ids:
        temp_ids.append(message.message_id)
        
    await state.update_data(edit_bot_message_ids=message_ids, edit_temp_message_ids=temp_ids)


# delete temp edit messages
async def _delete_temp_edit_messages(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    temp_ids = data.get("edit_temp_message_ids") or []
    if not temp_ids:
        return
    await delete_messages_fast(bot, chat_id, temp_ids)
    await state.update_data(edit_temp_message_ids=[])


# delete edit messages
async def _delete_edit_messages(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    message_ids = data.get("edit_bot_message_ids") or []
    if not message_ids:
        return
    await delete_messages_fast(bot, chat_id, message_ids)
    await state.update_data(edit_bot_message_ids=[])


def _is_valid_url(value: str) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


async def _submit_update_from_message(
    message: Message, state: FSMContext, session: AsyncSession
):
    if await state.get_state() != EventEdit.choosing_field:
        return
    data = await state.get_data()
    if not data.get("original_event_id"):
        await message.answer("Could not submit update. Please try again.")
        return
    await _perform_submit_edit(message, state, session)


async def _back_to_event_from_message(
    message: Message, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    event_id = data.get("original_event_id")
    if not event_id:
        await message.answer("Event not found.")
        return
    event = await get_event_by_id(session, event_id)
    if not event:
        await message.answer("Event not found.")
        return

    await state.set_state(None)
    delete_ids = [
        message.message_id,
        data.get("manage_event_msg_id"),
        data.get("admin_panel_msg_id"),
        *(data.get("edit_temp_message_ids") or []),
        *(data.get("edit_bot_message_ids") or []),
    ]
    keys_to_remove = [
        "original_event_id", "category_id", "category_name", "title",
        "description", "event_date", "event_time", "location",
        "organizer", "poster_file_id", "registration_url",
        "edit_use_reply_keyboard", "edit_bot_message_ids",
        "edit_temp_message_ids"
    ]
    for key in keys_to_remove:
        data.pop(key, None)
    data["manage_event_id"] = event_id
    await state.set_data(data)

    await delete_messages_fast(message.bot, message.chat.id, delete_ids, batch_size=20)

    # resend the event page fresh so that the event-management keyboard is restored
    if data.get("is_admin_edit"):
        from app.handlers.admin_panel import _show_admin_manage_event
        await _show_admin_manage_event(message, session, state, event_id, is_callback=False)
    else:
        from app.handlers.user_events import send_manage_event_message
        await send_manage_event_message(message, event, state=state, cleanup_previous=False)



# perform submit edit
async def _perform_submit_edit(
    message: Message, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    user = await upsert_user_from_telegram(session, message.from_user)

    original_event_id = data["original_event_id"]
    # convert stored strings back to date and time objects
    from datetime import datetime

    event_date = datetime.strptime(data["event_date"], "%Y-%m-%d").date()
    event_time = datetime.strptime(data["event_time"], "%H:%M").time()

    if data.get("is_admin_edit"):
        await acquire_event_lock(session, original_event_id)
        snapshot = await capture_event_snapshot(session, original_event_id)
        original_event = await get_event_by_id(session, original_event_id)
        if not original_event:
            await message.answer("Event not found.")
            return
            
        original_event.title = data["title"]
        original_event.description = data["description"]
        original_event.event_date = event_date
        original_event.event_time = event_time
        original_event.location = data["location"]
        original_event.category_id = data["category_id"]
        original_event.organizer_name = data["organizer"]
        if "poster_file_id" in data:
            original_event.poster_file_id = data.get("poster_file_id")
        if "registration_url" in data:
            original_event.registration_url = data.get("registration_url")

        session.add(
            ModerationLog(
                event_id=original_event.id,
                moderator_user_id=user.id,
                action=ModerationAction.EDITED.value,
                comment="Admin edited event",
            )
        )
        await enqueue_event_sync(
            session,
            event_id=original_event.id,
            operation="edited",
            snapshot=snapshot,
        )
        await session.commit()
        await state.set_state(None)
        
        # clear edit state but keep admin edit active
        await state.set_data({
            "is_admin_edit": True,
            "admin_active_events_mode": True,
            "manage_event_id": original_event_id,
            "my_events_choose_msg_id": data.get("my_events_choose_msg_id"),
            "my_events_selection_msg_id": data.get("my_events_selection_msg_id"),
            "my_events_cmd_msg_id": data.get("my_events_cmd_msg_id")
        })
        
        await message.answer("✅ Event updated immediately (Admin mode).")
        
        from app.handlers.admin_panel import _show_admin_manage_event
        await _show_admin_manage_event(message, session, state, original_event_id, is_callback=False)
        return

    draft = Event(
        creator_user_id=user.id,
        parent_event_id=original_event_id,
        title=data["title"],
        description=data["description"],
        event_date=event_date,
        event_time=event_time,
        location=data["location"],
        category_id=data["category_id"],
        organizer_name=data["organizer"],
        poster_file_id=data.get("poster_file_id"),
        registration_url=data.get("registration_url"),
        status=EventStatus.PENDING.value,
    )
    session.add(draft)
    await session.flush()
    draft_id = draft.id

    # record that this draft needs moderation before cleanup
    log = ModerationLog(
        event_id=draft.id,
        action=ModerationAction.SUBMITTED.value,
        comment="Draft update submitted",
    )
    session.add(log)
    await session.flush()

    # always remove any stale pending drafts for this parent so there is
    # never more than one pending version visible to users or admins
    await replace_pending_drafts_for_parent(session, original_event_id, draft_id)

    # if the parent event itself is still pending (original never approved)
    # detach the new draft and delete the old pending parent entirely
    parent_event = await get_event_by_id(session, original_event_id)
    if parent_event and parent_event.status == EventStatus.PENDING.value:
        await cleanup_previous_drafts(session, original_event_id, draft_id)

    await session.commit()
    await state.clear()
    await message.answer("Update submitted for moderation.")
    from app.handlers.start import send_main_menu
    await send_main_menu(message, session)


# submits an edit draft for moderation
# submit edit
@router.callback_query(EventEdit.choosing_field, F.data == "edit_submit")
async def submit_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    user = await upsert_user_from_telegram(session, callback.from_user)

    original_event_id = data["original_event_id"]
    await get_event_by_id(session, original_event_id)

    # convert stored strings back to date and time objects
    from datetime import datetime

    event_date = datetime.strptime(data["event_date"], "%Y-%m-%d").date()
    event_time = datetime.strptime(data["event_time"], "%H:%M").time()

    if data.get("is_admin_edit"):
        await acquire_event_lock(session, original_event_id)
        snapshot = await capture_event_snapshot(session, original_event_id)
        original_event = await get_event_by_id(session, original_event_id)
        if not original_event:
            await callback.answer("Event not found.", show_alert=True)
            return
            
        original_event.title = data["title"]
        original_event.description = data["description"]
        original_event.event_date = event_date
        original_event.event_time = event_time
        original_event.location = data["location"]
        original_event.category_id = data["category_id"]
        original_event.organizer_name = data["organizer"]
        if "poster_file_id" in data:
            original_event.poster_file_id = data.get("poster_file_id")
        if "registration_url" in data:
            original_event.registration_url = data.get("registration_url")

        session.add(
            ModerationLog(
                event_id=original_event.id,
                moderator_user_id=user.id,
                action=ModerationAction.EDITED.value,
                comment="Admin edited event",
            )
        )
        await enqueue_event_sync(
            session,
            event_id=original_event.id,
            operation="edited",
            snapshot=snapshot,
        )
        await session.commit()
        await state.set_state(None)
        
        # clear edit state but keep admin edit active
        await state.set_data({
            "is_admin_edit": True,
            "admin_active_events_mode": True,
            "manage_event_id": original_event_id,
            "my_events_choose_msg_id": data.get("my_events_choose_msg_id"),
            "my_events_selection_msg_id": data.get("my_events_selection_msg_id"),
            "my_events_cmd_msg_id": data.get("my_events_cmd_msg_id")
        })
        
        await callback.message.answer("✅ Event updated immediately (Admin mode).")
        await callback.answer()
        
        from app.handlers.admin_panel import _show_admin_manage_event
        await _show_admin_manage_event(callback.message, session, state, original_event_id, is_callback=False)
        return

    # create the draft event
    draft = Event(
        creator_user_id=user.id,
        parent_event_id=original_event_id,
        title=data["title"],
        description=data["description"],
        event_date=event_date,
        event_time=event_time,
        location=data["location"],
        category_id=data["category_id"],
        organizer_name=data["organizer"],
        poster_file_id=data.get("poster_file_id"),
        registration_url=data.get("registration_url"),
        status=EventStatus.PENDING.value,
    )
    session.add(draft)
    await session.flush()
    draft_id = draft.id

    # record that this draft needs moderation before cleanup
    log = ModerationLog(
        event_id=draft.id,
        action=ModerationAction.SUBMITTED.value,
        comment="Draft update submitted",
    )
    session.add(log)
    await session.flush()

    # always remove any stale pending drafts for this parent so there is
    # never more than one pending version visible to users or admins
    await replace_pending_drafts_for_parent(session, original_event_id, draft_id)

    # if the parent event itself is still pending (original never approved)
    # detach the new draft and delete the old pending parent entirely
    parent_event = await get_event_by_id(session, original_event_id)
    if parent_event and parent_event.status == EventStatus.PENDING.value:
        await cleanup_previous_drafts(session, original_event_id, draft_id)

    await session.commit()
    await state.clear()

    await callback.message.answer("Your update has been submitted for moderation.")
    await callback.answer()
    from app.handlers.start import send_main_menu
    await send_main_menu(callback.message, session)
