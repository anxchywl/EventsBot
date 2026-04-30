from aiogram import F, Router
import html

from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.enums import EventStatus, ModerationAction
from app.models.event import Event
from app.models.moderation import ModerationLog
from app.services.events import get_event_by_id
from app.services.users import upsert_user_from_telegram

router = Router(name="event_edit")


class EventEdit(StatesGroup):
    choosing_field = State()
    editing_title = State()
    editing_description = State()
    editing_date = State()
    editing_time = State()
    editing_location = State()
    editing_organizer = State()
    editing_poster = State()


@router.callback_query(F.data.startswith("edit_event_"))
async def start_edit_event(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    event_id = int(callback.data.split("_")[2])
    event = await get_event_by_id(session, event_id)

    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    if event.status not in (
        EventStatus.APPROVED.value,
        EventStatus.PENDING.value,
        EventStatus.NEEDS_CHANGES.value,
        EventStatus.REJECTED.value,
    ):
        await callback.answer(
            f"Cannot edit event in '{event.status}' status.", show_alert=True
        )
        return

        # initialize state data with current event values
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
    )

    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(callback.message, state, is_new_message=False)
    await callback.answer()


async def show_edit_menu(
    message: Message, state: FSMContext, is_new_message: bool = True
):
    data = await state.get_data()

    safe_title = html.escape(data["title"])
    safe_desc = html.escape(data["description"])
    safe_location = html.escape(data["location"])
    safe_organizer = html.escape(data["organizer"])
    safe_cat = html.escape(data["category_name"])

    text = (
        f"📝 <b>Editing Event</b>\n\n"
        f"<b>Title:</b> {safe_title}\n"
        f"<b>Description:</b> {safe_desc[:50]}...\n"
        f"<b>Date:</b> {data['event_date']}\n"
        f"<b>Time:</b> {data['event_time']}\n"
        f"<b>Location:</b> {safe_location}\n"
        f"<b>Organizer:</b> {safe_organizer}\n"
        f"<b>Category:</b> {safe_cat}\n"
        f"<b>Poster:</b> {'Provided' if data.get('poster_file_id') else 'None'}\n\n"
        f"Select a field to edit, or submit the update when you're done."
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Title", callback_data="edit_field_title")
    builder.button(text="✏️ Description", callback_data="edit_field_description")
    builder.button(text="✏️ Date", callback_data="edit_field_date")
    builder.button(text="✏️ Time", callback_data="edit_field_time")
    builder.button(text="✏️ Location", callback_data="edit_field_location")
    builder.button(text="✏️ Organizer", callback_data="edit_field_organizer")
    # category and poster can be added later, keep it simple for now
    builder.button(text="🖼 Poster", callback_data="edit_field_poster")

    builder.button(text="✅ Submit Update", callback_data="edit_submit")
    builder.button(text="❌ Cancel", callback_data="edit_cancel")
    builder.adjust(2, 2, 2, 1, 1, 1)

    if is_new_message:
        await message.answer(
            text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )
    else:
        await message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )


@router.callback_query(EventEdit.choosing_field, F.data.startswith("edit_field_"))
async def process_edit_field_choice(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[2]

    states_map = {
        "title": EventEdit.editing_title,
        "description": EventEdit.editing_description,
        "date": EventEdit.editing_date,
        "time": EventEdit.editing_time,
        "location": EventEdit.editing_location,
        "organizer": EventEdit.editing_organizer,
        "poster": EventEdit.editing_poster,
    }

    next_state = states_map.get(field)
    if next_state:
        await state.set_state(next_state)
        prompt = f"Please send the new {field}:"
        if field == "date":
            prompt = (
                "Please send the new date in **DD.MM.YYYY** format (e.g., 31.12.2023):"
            )
        elif field == "time":
            prompt = "Please send the new time in **HH:MM** format (e.g., 18:30):"

        await callback.message.answer(prompt, parse_mode="Markdown")
        await callback.answer()

    else:
        await callback.answer("Not implemented yet.", show_alert=True)

        # generic handler for text inputs during edit


@router.message(
    StateFilter(
        EventEdit.editing_title,
        EventEdit.editing_description,
        EventEdit.editing_date,
        EventEdit.editing_time,
        EventEdit.editing_location,
        EventEdit.editing_organizer,
    )
)
async def process_text_edit(message: Message, state: FSMContext):
    current_state = await state.get_state()
    field = current_state.split(":")[1].replace("editing_", "")

    from zoneinfo import ZoneInfo
    from app.config import get_settings
    from datetime import datetime, timedelta

    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    now = datetime.now(tz)

    if field == "date":
        try:
            val = datetime.strptime(message.text, "%d.%m.%Y").date()
            if val < now.date():
                await message.answer("Date cannot be in the past.")
                return
            if val > now.date() + timedelta(days=365):
                await message.answer("Date cannot be more than 1 year in the future.")
                return
            await state.update_data(event_date=val.isoformat())
        except ValueError:
            await message.answer("Please use DD.MM.YYYY format (e.g., 31.12.2023).")
            return
        field = "event_date"
    elif field == "time":
        try:
            val = datetime.strptime(message.text, "%H:%M").time()
            data = await state.get_data()
            event_date = datetime.strptime(data["event_date"], "%Y-%m-%d").date()
            if event_date == now.date() and val < now.time():
                await message.answer("Time cannot be in the past for today.")
                return
            await state.update_data(event_time=val.strftime("%H:%M"))
        except ValueError:
            await message.answer("Please use HH:MM format (e.g., 18:30).")
            return
        field = "event_time"

    if field == "title":
        if len(message.text) > 100:
            await message.answer("Title is too long. Max 100 characters.")
            return
        await state.update_data(title=message.text)
    elif field == "description":
        if len(message.text) > 1000:
            await message.answer("Description is too long. Max 1000 characters.")
            return
        await state.update_data(description=message.text)
    elif field == "event_date":
        pass
    elif field == "event_time":
        await state.update_data(event_time=message.text)
    elif field == "location":
        if len(message.text) > 100:
            await message.answer("Location is too long. Max 100 characters.")
            return
        await state.update_data(location=message.text)
    elif field == "organizer":
        if len(message.text) > 100:
            await message.answer("Organizer name is too long. Max 100 characters.")
            return
        await state.update_data(organizer=message.text)

    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(message, state, is_new_message=True)


@router.message(EventEdit.editing_poster, F.photo)
async def process_poster_edit(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(poster_file_id=photo_id)
    await state.set_state(EventEdit.choosing_field)
    await show_edit_menu(message, state, is_new_message=True)


@router.callback_query(EventEdit.choosing_field, F.data == "edit_cancel")
async def cancel_edit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Edit cancelled.")


@router.callback_query(EventEdit.choosing_field, F.data == "edit_submit")
async def submit_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    user = await upsert_user_from_telegram(session, callback.from_user)

    original_event_id = data["original_event_id"]
    await get_event_by_id(session, original_event_id)

    from datetime import datetime

    event_date = datetime.strptime(data["event_date"], "%Y-%m-%d").date()
    event_time = datetime.strptime(data["event_time"], "%H:%M").time()

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
    await session.flush()  # to get draft.id

    log = ModerationLog(
        event_id=draft.id,
        action=ModerationAction.SUBMITTED.value,
        comment="Draft update submitted",
    )
    session.add(log)
    await session.commit()

    await state.clear()
    await callback.message.edit_text("Your update has been submitted for moderation.")

    # notify moderators
    settings = get_settings()
    if settings.moderator_chat_id:
        from app.handlers.moderation import get_moderation_keyboard

        text = (
            f"🔔 **Event Update Request #{draft.id}**\n\n"
            f"**User:** {user.first_name} (@{user.username})\n"
            f"**Original Event:** #{original_event_id}\n\n"
            f"**New Title:** {draft.title}\n"
            f"**New Date:** {draft.event_date} {draft.event_time}\n"
            f"**New Description:**\n{draft.description[:200]}..."
        )
        try:
            await callback.bot.send_message(
                chat_id=settings.moderator_chat_id,
                text=text,
                reply_markup=get_moderation_keyboard(draft.id),
                parse_mode="Markdown",
            )
        except Exception as e:
            import logging

            logging.error(f"Failed to notify moderators: {e}")
