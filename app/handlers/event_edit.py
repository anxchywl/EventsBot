from aiogram import F, Router
import html

from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from urllib.parse import urlparse

from app.config import get_settings
from app.models.enums import EventStatus, ModerationAction
from app.models.event import Event
from app.models.moderation import ModerationLog
from app.services.events import get_event_by_id, cleanup_previous_drafts, replace_pending_drafts_for_parent
from app.services.users import upsert_user_from_telegram

router = Router(name="event_edit")


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

    old_data = await state.get_data()
    manage_event_msg_id = old_data.get("manage_event_msg_id")
    my_events_choose_msg_id = old_data.get("my_events_choose_msg_id")
    my_events_selection_msg_id = old_data.get("my_events_selection_msg_id")
    my_events_cmd_msg_id = old_data.get("my_events_cmd_msg_id")

    # Preserve admin-specific fields
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
        # Preserve admin-specific fields
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
@router.callback_query(EventEdit.choosing_field, F.data.startswith("edit_field_"))
async def process_edit_field_choice(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await _process_edit_field_choice(callback.data.split("_")[2], callback.message, state, session)
    await callback.answer()


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
@router.message(StateFilter(EventEdit.choosing_field))
async def invalid_choosing_field_edit(message: Message, state: FSMContext):
    await _record_temp_edit_message(state, message)
    sent = await message.answer("Please use the panels/keyboard to select an option. There is no such option as you wrote.")
    await _record_temp_edit_message(state, sent)


async def _process_edit_field_choice(field: str, message: Message, state: FSMContext, session: AsyncSession):
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
        # Delete temporary wrong inputs and warnings from the previous steps
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
            
            sent = await message.answer(
                "Please choose a new category for the event:",
                reply_markup=builder.as_markup(resize_keyboard=True),
            )
            await _record_edit_message(state, sent)
            return

        prompt = f"Please send the new {field.replace('_', ' ')}:"
        if field == "date":
            prompt = (
                "Please send the new date in **DD.MM.YYYY** format or **DD MM YYYY** format (e.g., 31.12.2023):"
            )
        elif field == "time":
            prompt = "Please send the new time in **HH:MM** format or **HH MM** format (e.g., 18:30):"
        elif field == "registration_link":
            prompt = (
                "Please send the new registration link in full URL form (https://...)."
            )

        sent = await message.answer(prompt, parse_mode="Markdown")
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
async def process_text_edit(message: Message, state: FSMContext):
    # Track this answer so it can still be deleted when the user cancels.
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
        raw_text = message.text.strip()
        clean_text = raw_text.replace(" ", ".")
        try:
            val = datetime.strptime(clean_text, "%d.%m.%Y").date()
            if val < now.date():
                await _record_temp_edit_message(state, message)
                sent = await message.answer("Date cannot be in the past.")
                await _record_temp_edit_message(state, sent)
                return
            if val > now.date() + timedelta(days=365):
                await _record_temp_edit_message(state, message)
                sent = await message.answer("Date cannot be more than 1 year in the future.")
                await _record_temp_edit_message(state, sent)
                return
            await state.update_data(event_date=val.isoformat())
        except ValueError:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Please use DD.MM.YYYY or DD MM YYYY format (e.g., 31.12.2023 or 31 12 2023).")
            await _record_temp_edit_message(state, sent)
            return
        field = "event_date"
    elif field == "time":
        raw_text = message.text.strip()
        clean_text = raw_text.replace(" ", ":")
        try:
            val = datetime.strptime(clean_text, "%H:%M").time()
            data = await state.get_data()
            event_date = datetime.strptime(data["event_date"], "%Y-%m-%d").date()
            if event_date == now.date() and val < now.time():
                await _record_temp_edit_message(state, message)
                sent = await message.answer("Time cannot be in the past for today.")
                await _record_temp_edit_message(state, sent)
                return
            await state.update_data(event_time=val.strftime("%H:%M"))
        except ValueError:
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Please use HH:MM or HH MM format (e.g., 18:30 or 18 30).")
            await _record_temp_edit_message(state, sent)
            return
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
        if not _is_valid_url(message.text):
            await _record_temp_edit_message(state, message)
            sent = await message.answer("Please send a valid URL that starts with http:// or https://")
            await _record_temp_edit_message(state, sent)
            return
        await state.update_data(registration_url=message.text)

    await _delete_temp_edit_messages(state, message.bot, message.chat.id)

    # return to the edit menu after each successful change without deleting intermediate edits
    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(message, state, is_new_message=True)


# validates and stores category edit
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
@router.message(EventEdit.editing_poster, ~F.photo)
async def invalid_poster_edit(message: Message, state: FSMContext):
    await _record_temp_edit_message(state, message)
    sent = await message.answer("Please send a valid photo for the poster.")
    await _record_temp_edit_message(state, sent)


# stores a replacement poster
@router.message(EventEdit.editing_poster, F.photo)
async def process_poster_edit(message: Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass
    await _delete_temp_edit_messages(state, message.bot, message.chat.id)
    photo_id = message.photo[-1].file_id
    await state.update_data(poster_file_id=photo_id)
    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(message, state, is_new_message=True)


# cancels the edit workflow / Back to Event
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
            
            # Edit the message back to the clean event card details
            import html
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            safe_title = html.escape(event.title)
            safe_location = html.escape(event.location)
            safe_cat = html.escape(event.category.name)
            safe_desc = html.escape(event.description)

            if data.get("is_admin_edit"):
                # Clean up edit message and resend the admin panel manage event view
                await callback.message.delete()
                from app.handlers.admin_panel import _show_admin_manage_event
                await _show_admin_manage_event(callback.message, session, state, event.id, is_callback=False)
                await callback.answer()
                return

            text = (
                f"<b>{safe_title}</b>\n\n"
                f"Date: {event.event_date}\n"
                f"Time: {event.event_time}\n"
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


async def _record_edit_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    message_ids = list(data.get("edit_bot_message_ids", []))
    if message.message_id not in message_ids:
        message_ids.append(message.message_id)
    await state.update_data(edit_bot_message_ids=message_ids)


async def _record_temp_edit_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    
    # Record in general bot message list
    message_ids = list(data.get("edit_bot_message_ids", []))
    if message.message_id not in message_ids:
        message_ids.append(message.message_id)
        
    # Record in temp/wrong messages list
    temp_ids = list(data.get("edit_temp_message_ids", []))
    if message.message_id not in temp_ids:
        temp_ids.append(message.message_id)
        
    await state.update_data(edit_bot_message_ids=message_ids, edit_temp_message_ids=temp_ids)


async def _delete_temp_edit_messages(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    temp_ids = data.get("edit_temp_message_ids") or []
    if not temp_ids:
        return
    for message_id in temp_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
    await state.update_data(edit_temp_message_ids=[])


async def _delete_edit_messages(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    message_ids = data.get("edit_bot_message_ids") or []
    if not message_ids:
        return
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
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

    # Delete the user's "Back to Event" reply command message
    try:
        await message.delete()
    except Exception:
        pass

    # 1. Delete the first sent event details card message
    card_msg_id = data.get("manage_event_msg_id")
    if card_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=card_msg_id)
        except Exception:
            pass

    admin_card_msg_id = data.get("admin_panel_msg_id")
    if admin_card_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=admin_card_msg_id)
        except Exception:
            pass

    # 2. Delete the edit menus and intermediate prompts/inputs
    await _delete_temp_edit_messages(state, message.bot, message.chat.id)
    await _delete_edit_messages(state, message.bot, message.chat.id)
    
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
    
    # 3. Resend the event page fresh so that panels pop open
    if data.get("is_admin_edit"):
        from app.handlers.admin_panel import _show_admin_manage_event
        await _show_admin_manage_event(message, session, state, event_id, is_callback=False)
    else:
        from app.handlers.user_events import send_manage_event_message
        await send_manage_event_message(message, event, state=state)



async def notify_moderators(bot, draft: Event, original_event_id: int, user):
    settings = get_settings()
    if settings.moderator_chat_id:
        from app.handlers.moderation import get_moderation_keyboard

        text = (
            f"Event Update Request #{draft.id}\n\n"
            f"User: {user.first_name} (@{user.username or 'none'})\n"
            f"Original Event: #{original_event_id}\n\n"
            f"New Title: {draft.title}\n"
            f"New Date: {draft.event_date} {draft.event_time}\n"
            f"New Description:\n{draft.description[:200]}..."
        )
        try:
            await bot.send_message(
                chat_id=settings.moderator_chat_id,
                text=text,
                reply_markup=get_moderation_keyboard(draft.id),
                parse_mode="Markdown",
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to notify moderators: {e}")


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

    # record that this draft needs moderation BEFORE cleanup
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

    # if the parent event itself is still pending (original never approved),
    # detach the new draft and delete the old pending parent entirely
    parent_event = await get_event_by_id(session, original_event_id)
    if parent_event and parent_event.status == EventStatus.PENDING.value:
        await cleanup_previous_drafts(session, original_event_id, draft_id)

    await session.commit()
    await state.clear()
    await message.answer("Update submitted for moderation.")
    from app.handlers.start import send_main_menu
    await send_main_menu(message, session)
    await notify_moderators(message.bot, draft, original_event_id, user)


# submits an edit draft for moderation
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

    # record that this draft needs moderation BEFORE cleanup
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

    # if the parent event itself is still pending (original never approved),
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

    # notify moderators
    await notify_moderators(callback.bot, draft, original_event_id, user)
