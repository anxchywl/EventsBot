import logging
from datetime import datetime
import html


from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.events import (
    create_pending_event,
    get_active_categories,
    get_category_by_id,
)
from app.services.users import upsert_user_from_telegram

router = Router()
logger = logging.getLogger(__name__)


# tracks states for the event submission form
class EventSubmission(StatesGroup):
    title = State()
    description = State()
    date = State()
    time = State()
    location = State()
    category = State()
    organizer = State()
    poster = State()
    registration_link = State()
    confirm = State()
    cancelled = State()


# clears the previous prompt and temporary errors
async def finalize_previous_step(
    state: FSMContext, bot: Bot, chat_id: int, summary_text: str = None
):
    """
    removes keyboards from all previous prompts, updates the last prompt with summary text,
    and clears any temporary error messages.
    """
    data = await state.get_data()
    prompt_ids = data.get("prompt_ids", [])
    temp_ids = data.get("temp_message_ids", [])

    # delete all temporary messages from bottom to top
    for t_id in reversed(temp_ids):
        try:
            await bot.delete_message(chat_id, t_id)
        except Exception:
            pass

    await state.update_data(temp_message_ids=[])

    if not prompt_ids:
        return

    p_id = prompt_ids[-1]

    # update the most recent prompt with a short summary
    try:
        if summary_text:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=p_id,
                text=summary_text,
                parse_mode="Markdown",
            )
        else:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=p_id, reply_markup=None
            )
    except Exception:
        pass

    await state.update_data(prompt_ids=[])


# stores message ids used during the submission flow
async def track_messages(
    state: FSMContext, *message_ids: int, is_prompt: bool = False, is_temp: bool = False
):
    """
    tracks message ids for deletion.
    """
    data = await state.get_data()
    messages = data.get("session_messages", [])
    prompt_ids = data.get("prompt_ids", [])
    temp_ids = data.get("temp_message_ids", [])

    # track flow messages for cleanup
    for m_id in message_ids:
        if m_id not in messages:
            messages.append(m_id)
        if is_temp and m_id not in temp_ids:
            temp_ids.append(m_id)

    # track the active prompt separately from temporary errors
    if is_prompt:
        last_bot_msg_id = message_ids[-1]
        if last_bot_msg_id not in prompt_ids:
            prompt_ids.append(last_bot_msg_id)

    await state.update_data(
        session_messages=messages, prompt_ids=prompt_ids, temp_message_ids=temp_ids
    )


# builds the cancel keyboard for submission prompts
def get_cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Back to Menu", callback_data="submit_cancel")
    return builder.as_markup()


# starts event creation from the main menu
@router.callback_query(F.data == "menu_create")
async def process_menu_create(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    categories = await get_active_categories(session)
    if not categories:
        await callback.answer("No categories available.", show_alert=True)
        return

    # reset form state before starting
    await state.clear()
    await state.update_data(
        session_messages=[], prompt_ids=[], temp_message_ids=[], start_from_menu=True
    )

    text = "Let's create a new event! What is the **title** of the event?"

    await callback.message.edit_text(
        text, reply_markup=get_cancel_kb(), parse_mode="Markdown"
    )

    await track_messages(state, callback.message.message_id, is_prompt=True)
    await state.set_state(EventSubmission.title)
    await callback.answer()


# starts event creation from the submit command
@router.message(Command("submit_event"), F.chat.type == "private")
async def cmd_submit_event(message: Message, state: FSMContext, session: AsyncSession):
    categories = await get_active_categories(session)
    if not categories:
        await message.answer(
            "No categories available. Please contact an administrator."
        )
        return

    # reset form state before starting
    await state.clear()
    await state.update_data(
        session_messages=[], prompt_ids=[], temp_message_ids=[], start_from_menu=False
    )

    msg = await message.answer(
        "Let's create a new event! What is the **title** of the event?",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.title)


# saves the event title
@router.message(EventSubmission.title, F.text)
async def process_title(message: Message, state: FSMContext, bot: Bot):
    # keep titles short for dashboard buttons
    if len(message.text) > 100:
        msg = await message.answer(
            "Title is too long. Please keep it under 100 characters."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, f"📝 **Title:** {message.text}"
    )

    # store the title and ask for description
    await state.update_data(title=message.text)
    msg = await message.answer(
        "Great! Now send me a **description** of the event.",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.description)


# saves the event description
@router.message(EventSubmission.description, F.text)
async def process_description(message: Message, state: FSMContext, bot: Bot):
    # keep descriptions within telegram message limits
    if len(message.text) > 1000:
        msg = await message.answer(
            "Description is too long. Please keep it under 1000 characters."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, "✅ **Description received.**"
    )

    # store the description and ask for date
    await state.update_data(description=message.text)
    msg = await message.answer(
        "When will the event take place? Please send the **date** in DD.MM.YYYY format (e.g., 31.12.2023).",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.date)


# saves the event date
@router.message(EventSubmission.date, F.text)
async def process_date(message: Message, state: FSMContext, bot: Bot):
    # reject obviously invalid date input early
    if len(message.text) > 10:
        msg = await message.answer("Invalid date format. Please use DD.MM.YYYY.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    try:
        # parse the date using the expected local format
        event_date = datetime.strptime(message.text, "%d.%m.%Y").date()

        from zoneinfo import ZoneInfo
        from app.config import get_settings

        settings = get_settings()
        tz = ZoneInfo(settings.app_timezone)
        today = datetime.now(tz).date()

        # reject dates outside the allowed planning window
        if event_date < today:
            msg = await message.answer(
                "Date cannot be in the past. Please enter a future date."
            )
            await track_messages(
                state, message.message_id, msg.message_id, is_temp=True
            )
            return

        from datetime import timedelta

        if event_date > today + timedelta(days=365):
            msg = await message.answer("Date cannot be more than 1 year in the future.")
            await track_messages(
                state, message.message_id, msg.message_id, is_temp=True
            )
            return

        # save the accepted date
        await finalize_previous_step(
            state, bot, message.chat.id, f"📅 **Date:** {message.text}"
        )
        await state.update_data(event_date=event_date)
    except ValueError:
        msg = await message.answer(
            "Invalid date format. Please use DD.MM.YYYY (e.g., 31.12.2023)."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # ask for the start time after date validation
    msg = await message.answer(
        "What time will it start? Please send the **time** in HH:MM format (e.g., 18:30).",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.time)


# saves the event time
@router.message(EventSubmission.time, F.text)
async def process_time(message: Message, state: FSMContext, bot: Bot):
    # reject obviously invalid time input early
    if len(message.text) > 10:
        msg = await message.answer("Invalid time format. Please use HH:MM.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    try:
        # parse the time using the expected local format
        event_time = datetime.strptime(message.text, "%H:%M").time()

        data = await state.get_data()
        event_date = data.get("event_date")

        from zoneinfo import ZoneInfo
        from app.config import get_settings

        settings = get_settings()
        tz = ZoneInfo(settings.app_timezone)
        now = datetime.now(tz)

        # reject times that already passed today
        if event_date == now.date() and event_time < now.time():
            msg = await message.answer("Time cannot be in the past for today's date.")
            await track_messages(
                state, message.message_id, msg.message_id, is_temp=True
            )
            return

        # save the accepted time
        await finalize_previous_step(
            state, bot, message.chat.id, f"🕒 **Time:** {message.text}"
        )
        await state.update_data(event_time=event_time)
    except ValueError:
        msg = await message.answer(
            "Invalid time format. Please use HH:MM (e.g., 18:30)."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # ask for the location after time validation
    msg = await message.answer(
        "Where will the event be held? Please provide the **location**.",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.location)


# saves the event location
@router.message(EventSubmission.location, F.text)
async def process_location(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    # keep locations short for previews and dashboards
    if len(message.text) > 100:
        msg = await message.answer(
            "Location is too long. Please keep it under 100 characters."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, f"📍 **Location:** {message.text}"
    )
    # store location and show categories
    await state.update_data(location=message.text)

    categories = await get_active_categories(session)
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"cat_{cat.id}")
    builder.button(text="🔙 Back to Menu", callback_data="submit_cancel")
    builder.adjust(2)

    msg = await message.answer(
        "Please choose a **category** for your event:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.category)


# saves the selected category
@router.callback_query(EventSubmission.category, F.data.startswith("cat_"))
async def process_category(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
):
    category_id = int(callback.data.split("_")[1])
    category = await get_category_by_id(session, category_id)
    if not category:
        await callback.answer("Category not found.", show_alert=True)
        return

    # store category and ask for organizer
    await finalize_previous_step(
        state, bot, callback.message.chat.id, f"📁 **Category:** {category.name}"
    )

    await state.update_data(category_id=category.id, category_name=category.name)
    msg = await callback.message.answer(
        "Who is organizing the event? Send the **organizer or club name**.",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.organizer)
    await callback.answer()


# saves the organizer name
@router.message(EventSubmission.organizer, F.text)
async def process_organizer(message: Message, state: FSMContext, bot: Bot):
    await finalize_previous_step(
        state, bot, message.chat.id, f"🏢 **Organizer:** {message.text}"
    )

    await state.update_data(organizer=message.text)

    # show poster choices
    builder = InlineKeyboardBuilder()
    builder.button(text="Skip poster", callback_data="skip_poster")
    builder.button(text="🔙 Back to Menu", callback_data="submit_cancel")
    builder.adjust(1)

    msg = await message.answer(
        "Please send a **poster or image** for the event. If you don't have one, click Skip.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.poster)


# saves the uploaded poster
@router.message(EventSubmission.poster, F.photo)
async def process_poster(message: Message, state: FSMContext, bot: Bot):
    # use the highest resolution telegram photo
    file_id = message.photo[-1].file_id
    await state.update_data(poster_file_id=file_id)
    await finalize_previous_step(state, bot, message.chat.id, "🖼️ **Poster uploaded.**")
    await prompt_registration_link(message, state, bot)


# skips poster upload
@router.callback_query(EventSubmission.poster, F.data == "skip_poster")
async def skip_poster(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(poster_file_id=None)
    await finalize_previous_step(
        state, bot, callback.message.chat.id, "🖼️ **No poster (skipped).**"
    )
    await prompt_registration_link(callback.message, state, bot)
    await callback.answer()


# asks for an optional registration link
async def prompt_registration_link(message_obj: Message, state: FSMContext, bot: Bot):
    builder = InlineKeyboardBuilder()
    builder.button(text="Skip link", callback_data="skip_link")
    builder.button(text="🔙 Back to Menu", callback_data="submit_cancel")
    builder.adjust(1)
    msg = await message_obj.answer(
        "If there is a **registration link**, please send it now. Otherwise, click Skip.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    # track the user message only when it came from a user
    if isinstance(message_obj, Message) and message_obj.from_user.is_bot is False:
        await track_messages(
            state, message_obj.message_id, msg.message_id, is_prompt=True
        )
    else:
        await track_messages(state, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.registration_link)


# saves the registration link
@router.message(EventSubmission.registration_link, F.text)
async def process_registration_link(message: Message, state: FSMContext, bot: Bot):
    await finalize_previous_step(
        state, bot, message.chat.id, f"🔗 **Link:** {message.text}"
    )
    await state.update_data(registration_url=message.text)
    await track_messages(state, message.message_id)
    await show_event_preview(message, state, bot)


# skips the registration link
@router.callback_query(EventSubmission.registration_link, F.data == "skip_link")
async def skip_registration_link(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(registration_url=None)
    await finalize_previous_step(
        state, bot, callback.message.chat.id, "🔗 **No link (skipped).**"
    )
    await show_event_preview(callback.message, state, bot)
    await callback.answer()


# shows the final event preview before submit
async def show_event_preview(message_obj: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()

    # escape user text before rendering html
    safe_title = html.escape(data["title"])
    safe_location = html.escape(data["location"])
    safe_organizer = html.escape(data["organizer"])
    safe_desc = html.escape(data["description"])

    preview_text = (
        f"📋 <b>Event Preview:</b>\n\n"
        f"<b>Title:</b> {safe_title}\n"
        f"<b>Date:</b> {data['event_date']} at {data['event_time']}\n"
        f"<b>Location:</b> {safe_location}\n"
        f"<b>Category:</b> {data['category_name']}\n"
        f"<b>Organizer:</b> {safe_organizer}\n\n"
        f"<b>Description:</b>\n{safe_desc}\n\n"
    )
    # add the registration link only when present
    if data.get("registration_url"):
        safe_url = html.escape(data["registration_url"])
        preview_text += f"<b>Registration:</b> {safe_url}\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Submit Event", callback_data="submit_confirm")
    builder.button(text="❌ Cancel", callback_data="submit_cancel")
    builder.adjust(2)

    # send the preview with poster when available
    if data.get("poster_file_id"):
        msg = await message_obj.answer_photo(
            data["poster_file_id"],
            caption=preview_text,
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
    else:
        msg = await message_obj.answer(
            preview_text, parse_mode="HTML", reply_markup=builder.as_markup()
        )

    await track_messages(state, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.confirm)


# creates the pending event after confirmation
@router.callback_query(EventSubmission.confirm, F.data == "submit_confirm")
async def confirm_submission(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
):
    data = await state.get_data()
    user = await upsert_user_from_telegram(session, callback.from_user)

    # save the event and show the user confirmation
    event = await create_pending_event(session, user, data)
    await session.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🎉 Your event has been submitted and is now pending moderation. You will be notified once it is approved!"
    )

    # notify moderators when a moderator chat is configured
    settings = get_settings()
    moderator_chat_id = getattr(settings, "moderator_chat_id", None)
    if moderator_chat_id:
        from app.handlers.moderation import get_moderation_keyboard

        try:
            text = (
                f"🔔 **New Event Submitted**\n\n"
                f"<b>Title:</b> {event.title}\n"
                f"<b>Creator:</b> {user.first_name} (@{user.username})\n"
                f"<b>ID:</b> {event.id}"
            )
            if event.poster_file_id:
                await bot.send_photo(
                    moderator_chat_id,
                    event.poster_file_id,
                    caption=text,
                    reply_markup=get_moderation_keyboard(event.id),
                    parse_mode="Markdown",
                )
            else:
                await bot.send_message(
                    moderator_chat_id,
                    text,
                    reply_markup=get_moderation_keyboard(event.id),
                    parse_mode="Markdown",
                )
        except Exception:
            pass

    await state.clear()
    await callback.answer()


# cancels the submission flow
@router.callback_query(F.data == "submit_cancel")
async def cancel_submission(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
):
    data = await state.get_data()
    messages = data.get("session_messages", [])
    start_from_menu = data.get("start_from_menu", False)

    for msg_id in reversed(messages):
        try:
            await bot.delete_message(callback.message.chat.id, msg_id)
        except Exception:
            pass

    if callback.message.message_id not in messages:
        try:
            await bot.delete_message(
                callback.message.chat.id, callback.message.message_id
            )
        except Exception:
            pass

    # rebuild the main menu when the flow started from it
    if start_from_menu:
        from app.handlers.start import get_main_menu_keyboard

        user = await upsert_user_from_telegram(session, callback.from_user)
        settings = get_settings()
        is_admin = user.telegram_id in settings.admin_ids

        await bot.send_message(
            callback.message.chat.id,
            "👋 **Welcome to the Student Events Bot!**\n\n"
            "I am here to help you stay updated with university life without the noise.\n\n"
            "Use the menu below to explore events or manage your own submissions.",
            reply_markup=get_main_menu_keyboard(is_admin),
            parse_mode="Markdown",
        )

    await state.clear()
    await callback.answer("Cancelled")
