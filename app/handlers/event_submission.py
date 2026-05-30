import logging
from datetime import datetime
from urllib.parse import urlparse
import html

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder

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
    current_prompt_id = data.get("current_prompt_id")
    previous_prompt_id = data.get("previous_prompt_id")

    # track flow messages for cleanup
    for m_id in message_ids:
        if m_id not in messages:
            messages.append(m_id)
        if is_temp and m_id not in temp_ids:
            temp_ids.append(m_id)

    # track the active prompt separately from temporary errors
    if is_prompt:
        if current_prompt_id:
            previous_prompt_id = current_prompt_id
        current_prompt_id = message_ids[-1]
        prompt_ids = [current_prompt_id]

    await state.update_data(
        session_messages=messages,
        prompt_ids=prompt_ids,
        temp_message_ids=temp_ids,
        current_prompt_id=current_prompt_id,
        previous_prompt_id=previous_prompt_id,
    )


# builds the cancel keyboard for submission prompts
def get_cancel_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Back to Menu")
    return builder.as_markup(resize_keyboard=True)


# builds a step keyboard with a Back button, an optional skip button, and cancel navigation
def get_step_navigation_kb(skip_text: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text="Back")
    builder.button(text=skip_text)
    builder.button(text="Back to Menu")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


# builds the confirmation keyboard for event preview
def get_confirm_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Back")
    builder.button(text="Submit Event")
    builder.button(text="Cancel")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


# builds a simple back + cancel keyboard for returning to an earlier step
def get_back_and_cancel_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Back")
    builder.button(text="Back to Menu")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


# starts event creation from the main menu (inline callback fallback)
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

    await callback.message.answer(
        text, reply_markup=get_cancel_kb(), parse_mode="Markdown"
    )

    await track_messages(state, callback.message.message_id, is_prompt=True)
    await state.set_state(EventSubmission.title)
    await callback.answer()


# starts event creation from the reply button or text command
@router.message(F.text == "Create Event", F.chat.type == "private")
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
        session_messages=[message.message_id], prompt_ids=[], temp_message_ids=[], start_from_menu=True
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
async def process_title(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return

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
    await state.update_data(title=message.text, last_step_user_message_id=message.message_id)
    msg = await message.answer(
        "Great! Now send me a **description** of the event.",
        reply_markup=get_back_and_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.description)


# saves the event description
@router.message(EventSubmission.description, F.text)
async def process_description(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    # keep descriptions within telegram message limits
    if len(message.text) > 1000:
        msg = await message.answer(
            "Description is too long. Please keep it under 1000 characters."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, "✓ **Description received.**"
    )

    # store the description and ask for date
    await state.update_data(description=message.text, last_step_user_message_id=message.message_id)
    msg = await message.answer(
        "When will the event take place? Please send the **date** in DD.MM.YYYY format or DD MM YYYY format (e.g., 31.12.2023 or 31 12 2023).",
        reply_markup=get_back_and_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.date)


# saves the event date
@router.message(EventSubmission.date, F.text)
async def process_date(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    # reject obviously invalid date input early
    if len(message.text) > 10:
        msg = await message.answer("Invalid date format. Please use DD.MM.YYYY or DD MM YYYY.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    raw_text = message.text.strip()
    clean_text = raw_text.replace(" ", ".")
    try:
        # parse the date using the expected local format
        event_date = datetime.strptime(clean_text, "%d.%m.%Y").date()

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
            state, bot, message.chat.id, f"📅 **Date:** {event_date.strftime('%d.%m.%Y')}"
        )
        await state.update_data(event_date=event_date, last_step_user_message_id=message.message_id)
        await track_messages(state, message.message_id)
    except ValueError:
        msg = await message.answer(
            "Invalid date format. Please use DD.MM.YYYY or DD MM YYYY (e.g., 31.12.2023 or 31 12 2023)."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # ask for the start time after date validation
    msg = await message.answer(
        "What time will it start? Please send the **time** in HH:MM or HH MM format (e.g., 18:30 or 18 30).",
        reply_markup=get_back_and_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.time)


# saves the event time
@router.message(EventSubmission.time, F.text)
async def process_time(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    # reject obviously invalid time input early
    if len(message.text) > 10:
        msg = await message.answer("Invalid time format. Please use HH:MM or HH MM.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    raw_text = message.text.strip()
    clean_text = raw_text.replace(" ", ":")
    try:
        # parse the time using the expected local format
        event_time = datetime.strptime(clean_text, "%H:%M").time()

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
            state, bot, message.chat.id, f"🕒 **Time:** {event_time.strftime('%H:%M')}"
        )
        await state.update_data(event_time=event_time, last_step_user_message_id=message.message_id)
        await track_messages(state, message.message_id)
    except ValueError:
        msg = await message.answer(
            "Invalid time format. Please use HH:MM or HH MM (e.g., 18:30 or 18 30)."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # ask for the location after time validation
    msg = await message.answer(
        "Where will the event be held? Please provide the **location**.",
        reply_markup=get_back_and_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.location)


# saves the event location
@router.message(EventSubmission.location, F.text)
async def process_location(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

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
    await state.update_data(location=message.text, last_step_user_message_id=message.message_id)
    await track_messages(state, message.message_id)

    categories = await get_active_categories(session)
    builder = ReplyKeyboardBuilder()
    builder.button(text="Back")
    for cat in categories:
        builder.button(text=cat.name)
    builder.button(text="Back to Menu")
    builder.adjust(1)

    msg = await message.answer(
        "Please choose a **category** for your event:",
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.category)


# saves the selected category
@router.message(EventSubmission.category, F.text)
async def process_category(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    categories = await get_active_categories(session)
    category = next((c for c in categories if c.name == message.text), None)
    if not category:
        msg = await message.answer("Category not found. Please choose from the keyboard.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # store category and ask for organizer
    await finalize_previous_step(
        state, bot, message.chat.id, f"📁 **Category:** {category.name}"
    )

    await state.update_data(category_id=category.id, category_name=category.name, last_step_user_message_id=message.message_id)
    await track_messages(state, message.message_id)
    msg = await message.answer(
        "Who is organizing the event? Send the **organizer or club name**.",
        reply_markup=get_back_and_cancel_kb(),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.organizer)


# saves the organizer name
@router.message(EventSubmission.organizer, F.text)
async def process_organizer(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, f"🏢 **Organizer:** {message.text}"
    )

    await state.update_data(organizer=message.text, last_step_user_message_id=message.message_id)
    await track_messages(state, message.message_id)
    await prompt_poster(message, state, bot)


# saves the uploaded poster
@router.message(EventSubmission.poster, F.photo)
async def process_poster(message: Message, state: FSMContext, bot: Bot):
    # use the highest resolution telegram photo
    file_id = message.photo[-1].file_id
    await state.update_data(poster_file_id=file_id, last_step_user_message_id=message.message_id)
    await track_messages(state, message.message_id)
    await finalize_previous_step(state, bot, message.chat.id, "🖼️ **Poster uploaded.**")
    await prompt_registration_link(message, state, bot)


# skips poster upload
@router.message(EventSubmission.poster, F.text == "Skip poster")
async def skip_poster(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await state.update_data(poster_file_id=None, last_step_user_message_id=message.message_id)
    await track_messages(state, message.message_id)
    await finalize_previous_step(
        state, bot, message.chat.id, "🖼️ **No poster (skipped).**"
    )
    await prompt_registration_link(message, state, bot)


# asks for a poster or image
async def prompt_poster(message_obj: Message, state: FSMContext, bot: Bot):
    builder = get_step_navigation_kb("Skip poster")
    msg = await message_obj.answer(
        "Please send a **poster or image** for the event. If you don't have one, click Skip.",
        reply_markup=builder,
        parse_mode="Markdown",
    )
    await track_messages(state, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.poster)


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


# asks for an optional registration link
async def prompt_registration_link(message_obj: Message, state: FSMContext, bot: Bot):
    builder = get_step_navigation_kb("Skip link")
    msg = await message_obj.answer(
        "If there is a **registration link**, please send it now. Otherwise, click Skip.",
        reply_markup=builder,
        parse_mode="Markdown",
    )
    await track_messages(state, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.registration_link)


async def go_back_one_step(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    data = await state.get_data()
    current_prompt_id = data.get("current_prompt_id")
    previous_prompt_id = data.get("previous_prompt_id")
    last_step_user_message_id = data.get("last_step_user_message_id")
    temp_ids = data.get("temp_message_ids", [])
    chat_id = message.chat.id

    for msg_id in filter(None, [message.message_id, current_prompt_id, previous_prompt_id, last_step_user_message_id]):
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    for t_id in reversed(temp_ids):
        try:
            await bot.delete_message(chat_id, t_id)
        except Exception:
            pass

    await state.update_data(
        current_prompt_id=None,
        previous_prompt_id=None,
        prompt_ids=[],
        temp_message_ids=[],
        last_step_user_message_id=None,
    )

    current_state = await state.get_state()
    if current_state == EventSubmission.confirm:
        await state.update_data(registration_url=None)
        await prompt_registration_link(message, state, bot)
        return

    if current_state == EventSubmission.registration_link:
        await state.update_data(poster_file_id=None)
        await prompt_poster(message, state, bot)
        return

    if current_state == EventSubmission.poster:
        await state.update_data(organizer=None)
        msg = await message.answer(
            "Who is organizing the event? Send the **organizer or club name**.",
            reply_markup=get_back_and_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await state.set_state(EventSubmission.organizer)
        return

    if current_state == EventSubmission.organizer:
        await state.update_data(category_id=None, category_name=None)
        categories = await get_active_categories(session)
        builder = ReplyKeyboardBuilder()
        builder.button(text="Back")
        for cat in categories:
            builder.button(text=cat.name)
        builder.button(text="Back to Menu")
        builder.adjust(1)
        msg = await message.answer(
            "Please choose a **category** for your event:",
            reply_markup=builder.as_markup(resize_keyboard=True),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await state.set_state(EventSubmission.category)
        return

    if current_state == EventSubmission.category:
        await state.update_data(location=None)
        msg = await message.answer(
            "Where will the event be held? Please provide the **location**.",
            reply_markup=get_back_and_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await state.set_state(EventSubmission.location)
        return

    if current_state == EventSubmission.location:
        await state.update_data(event_time=None)
        msg = await message.answer(
            "What time will it start? Please send the **time** in HH:MM or HH MM format (e.g., 18:30 or 18 30).",
            reply_markup=get_back_and_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await state.set_state(EventSubmission.time)
        return

    if current_state == EventSubmission.time:
        await state.update_data(event_date=None)
        msg = await message.answer(
            "When will the event take place? Please send the **date** in DD.MM.YYYY format or DD MM YYYY format (e.g., 31.12.2023 or 31 12 2023).",
            reply_markup=get_back_and_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await state.set_state(EventSubmission.date)
        return

    if current_state == EventSubmission.date:
        await state.update_data(description=None)
        msg = await message.answer(
            "Great! Now send me a **description** of the event.",
            reply_markup=get_back_and_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await state.set_state(EventSubmission.description)
        return

    if current_state == EventSubmission.description:
        await state.update_data(title=None)
        msg = await message.answer(
            "Let's create a new event! What is the **title** of the event?",
            reply_markup=get_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await state.set_state(EventSubmission.title)
        return


@router.message(EventSubmission.poster, F.text == "Back")
async def back_from_poster(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.registration_link, F.text == "Back")
async def back_from_registration(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.confirm, F.text == "Back")
async def back_from_preview(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.organizer, F.text == "Back")
async def back_from_organizer(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.category, F.text == "Back")
async def back_from_category(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.location, F.text == "Back")
async def back_from_location(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.time, F.text == "Back")
async def back_from_time(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.date, F.text == "Back")
async def back_from_date(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.description, F.text == "Back")
async def back_from_description(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    await go_back_one_step(message, state, bot, session)


@router.message(EventSubmission.poster)
async def invalid_poster_input(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    msg = await message.answer(
        "Please send a poster image or click Skip poster. If you don't have one, click Skip.",
        reply_markup=get_step_navigation_kb("Skip poster"),
        parse_mode="Markdown",
    )
    await track_messages(state, message.message_id, msg.message_id, is_temp=True)


# saves the registration link
@router.message(EventSubmission.registration_link, F.text)
async def process_registration_link(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return
    if message.text == "Skip link":
        await skip_registration_link(message, state, bot)
        return

    if not is_valid_url(message.text):
        msg = await message.answer(
            "That doesn't look like a valid link. Please send a full URL starting with http:// or https://, or click Skip link.",
            reply_markup=get_step_navigation_kb("Skip link"),
            parse_mode="Markdown",
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await state.update_data(registration_url=message.text, last_step_user_message_id=message.message_id)
    await finalize_previous_step(
        state, bot, message.chat.id, f"🔗 **Link:** {message.text}"
    )
    await track_messages(state, message.message_id)
    await show_event_preview(message, state, bot)


# skips the registration link
async def skip_registration_link(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(registration_url=None, last_step_user_message_id=message.message_id)
    await track_messages(state, message.message_id)
    await finalize_previous_step(
        state, bot, message.chat.id, "🔗 **No link (skipped).**"
    )
    await show_event_preview(message, state, bot)


# shows the final event preview before submit
async def show_event_preview(message_obj: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()

    # escape user text before rendering html
    safe_title = html.escape(data["title"])
    safe_location = html.escape(data["location"])
    safe_organizer = html.escape(data["organizer"])
    safe_desc = html.escape(data["description"])

    preview_text = (
        f"<b>Event Preview</b>\n\n"
        f"<b>Title:</b> {safe_title}\n"
        f"<b>Date:</b> {data['event_date'].strftime('%d.%m.%Y')} at {data['event_time'].strftime('%H:%M')}\n"
        f"<b>Location:</b> {safe_location}\n"
        f"<b>Category:</b> {data['category_name']}\n"
        f"<b>Organizer:</b> {safe_organizer}\n\n"
        f"<b>Description:</b>\n{safe_desc}\n\n"
    )
    # add the registration link only when present
    if data.get("registration_url"):
        safe_url = html.escape(data["registration_url"])
        preview_text += f"<b>Registration:</b> {safe_url}\n"

    builder = get_confirm_kb()

    # send the preview with poster when available
    if data.get("poster_file_id"):
        msg = await message_obj.answer_photo(
            data["poster_file_id"],
            caption=preview_text,
            parse_mode="HTML",
            reply_markup=builder,
        )
    else:
        msg = await message_obj.answer(
            preview_text, parse_mode="HTML", reply_markup=builder
        )

    await track_messages(state, msg.message_id, is_prompt=True)
    await state.set_state(EventSubmission.confirm)


# creates the pending event after confirmation
@router.message(EventSubmission.confirm, F.text == "Submit Event")
async def confirm_submission(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    data = await state.get_data()
    user = await upsert_user_from_telegram(session, message.from_user)

    # save the event and show the user confirmation
    event = await create_pending_event(session, user, data)
    await session.commit()

    from app.handlers.start import get_main_menu_keyboard
    settings = get_settings()
    is_admin = user.telegram_id in settings.admin_ids

    await message.answer(
        "🎉 Your event has been submitted and is now pending moderation. You will be notified once it is approved!",
        reply_markup=get_main_menu_keyboard(is_admin)
    )

    # notify moderators when a moderator chat is configured
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


# cancels the submission flow via message or text button (fully deletes all intermediate chat history)
@router.message(EventSubmission.confirm, F.text == "Cancel")
async def cancel_submission_message(
    message: Message, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    messages = data.get("session_messages", [])

    # delete all interactive user responses and bot prompts from this submission session
    for msg_id in reversed(messages):
        try:
            await message.bot.delete_message(message.chat.id, msg_id)
        except Exception:
            pass

    # delete the user's triggering "Back to Menu" / "Cancel" text message
    try:
        await message.delete()
    except Exception:
        pass

    # delete the previous Welcome message to avoid duplicates
    from app.handlers.start import last_welcome_messages, send_main_menu
    welcome_msg_id = last_welcome_messages.get(message.from_user.id)
    if welcome_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, welcome_msg_id)
        except Exception:
            pass

    await state.clear()
    await send_main_menu(message, session)
