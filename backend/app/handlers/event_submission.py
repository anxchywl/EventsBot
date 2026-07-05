import logging
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urlparse
import html
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.image_processing import process_image
from app.services.rate_limit import check_bot_rate_limit
from app.services.events import (
    create_pending_event,
    get_active_categories,
    get_category_by_id,
)
from app.services.event_cards import escape_and_fit_description
from app.services.users import upsert_user_from_telegram
from app.handlers.message_cleanup import delete_messages_fast

router = Router()
logger = logging.getLogger(__name__)

DATE_PROMPT = "Event date (DD MM YYYY)"
TIME_PROMPT = "Start time (HH MM)"
_DATE_RE = re.compile(r"^(\d{2}) (\d{2}) (\d{4})$")
_TIME_RE = re.compile(r"^(\d{2}) (\d{2})$")


def sanitize_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'[\x00-\x09\x0B-\x1F]+', '', text)
    return cleaned.strip()


class LimitedBytesIO(BytesIO):
    def __init__(self, max_size_bytes: int) -> None:
        super().__init__()
        self.max_size_bytes = max_size_bytes

    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > self.max_size_bytes:
            raise ValueError("File too large")
        return super().write(data)


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
    await delete_messages_fast(bot, chat_id, reversed(temp_ids))

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


# push nav prompt
async def push_nav_prompt(
    state: FSMContext,
    *,
    state_name: str,
    data_key: str | None,
    prompt_id: int,
) -> None:
    data = await state.get_data()
    stack = list(data.get("submission_nav_stack") or [])
    stack.append(
        {
            "state": state_name,
            "data_key": data_key,
            "prompt_id": prompt_id,
            "answer_id": None,
        }
    )
    await state.update_data(submission_nav_stack=stack)


# record nav answer
async def record_nav_answer(state: FSMContext, answer_id: int) -> None:
    data = await state.get_data()
    stack = list(data.get("submission_nav_stack") or [])
    if stack:
        stack[-1]["answer_id"] = answer_id
        await state.update_data(submission_nav_stack=stack)


# send submission prompt
async def send_submission_prompt(
    message: Message,
    state: FSMContext,
    step: str,
    session: AsyncSession | None = None,
) -> Message:
    if step == "title":
        msg = await message.answer(
            "Let's create a new event! What is the **title** of the event?",
            reply_markup=get_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await push_nav_prompt(
            state,
            state_name=EventSubmission.title.state,
            data_key="title",
            prompt_id=msg.message_id,
        )
        await state.set_state(EventSubmission.title)
        return msg

    if step == "description":
        msg = await message.answer(
            "Great! Now send me a **description** of the event.",
            reply_markup=get_back_and_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await push_nav_prompt(
            state,
            state_name=EventSubmission.description.state,
            data_key="description",
            prompt_id=msg.message_id,
        )
        await state.set_state(EventSubmission.description)
        return msg

    if step == "date":
        msg = await message.answer(
            DATE_PROMPT,
            reply_markup=get_back_and_cancel_kb(),
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await push_nav_prompt(
            state,
            state_name=EventSubmission.date.state,
            data_key="event_date",
            prompt_id=msg.message_id,
        )
        await state.set_state(EventSubmission.date)
        return msg

    if step == "time":
        msg = await message.answer(
            TIME_PROMPT,
            reply_markup=get_back_and_cancel_kb(),
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await push_nav_prompt(
            state,
            state_name=EventSubmission.time.state,
            data_key="event_time",
            prompt_id=msg.message_id,
        )
        await state.set_state(EventSubmission.time)
        return msg

    if step == "location":
        msg = await message.answer(
            "Where will the event be held? Please provide the **location**.",
            reply_markup=get_back_and_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await push_nav_prompt(
            state,
            state_name=EventSubmission.location.state,
            data_key="location",
            prompt_id=msg.message_id,
        )
        await state.set_state(EventSubmission.location)
        return msg

    if step == "category":
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
        await push_nav_prompt(
            state,
            state_name=EventSubmission.category.state,
            data_key="category_id",
            prompt_id=msg.message_id,
        )
        await state.set_state(EventSubmission.category)
        return msg

    if step == "organizer":
        msg = await message.answer(
            "Who is organizing the event? Send the **organizer or club name**.",
            reply_markup=get_back_and_cancel_kb(),
            parse_mode="Markdown",
        )
        await track_messages(state, msg.message_id, is_prompt=True)
        await push_nav_prompt(
            state,
            state_name=EventSubmission.organizer.state,
            data_key="organizer",
            prompt_id=msg.message_id,
        )
        await state.set_state(EventSubmission.organizer)
        return msg

    raise ValueError(f"Unknown submission step: {step}")


# parse event date input
def parse_event_date_input(value: str):
    match = _DATE_RE.fullmatch(value.strip())
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


# parse event time input
def parse_event_time_input(value: str):
    match = _TIME_RE.fullmatch(value.strip())
    if not match:
        return None
    hour, minute = map(int, match.groups())
    if hour > 23 or minute > 59:
        return None
    return datetime(2000, 1, 1, hour, minute).time()


# builds the cancel keyboard for submission prompts
def get_cancel_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Back to Menu")
    return builder.as_markup(resize_keyboard=True)


# builds a step keyboard with a back button, an optional skip button, and cancel navigation
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
# process menu create
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
        session_messages=[],
        prompt_ids=[],
        temp_message_ids=[],
        submission_nav_stack=[],
        start_from_menu=True,
    )

    await send_submission_prompt(callback.message, state, "title")
    await callback.answer()


# starts event creation from the reply button or text command
# cmd submit event
@router.message(F.text == "Create Event", F.chat.type == "private")
@router.message(Command("submit_event"), F.chat.type == "private")
async def cmd_submit_event(message: Message, state: FSMContext, session: AsyncSession):
    # DISABLED (client refactor): event creation moved out of the bot. The
    # "Create Event" keyboard button was removed; this guard blocks the flow from
    # being triggered by manually typing the text or /submit_event. Remove this
    # early return (and restore the keyboard button in start.py) to re-enable.
    return

    if not await check_bot_rate_limit(message.from_user.id, "event_submit", 5, 3600):
        await message.answer(
            "You've reached the event submission limit. Try again later."
        )
        return
    categories = await get_active_categories(session)
    if not categories:
        await message.answer(
            "No categories available. Please contact an administrator."
        )
        return

    from app.handlers.start import cleanup_main_menu_warnings

    await cleanup_main_menu_warnings(message, state)

    # reset form state before starting
    await state.clear()
    await state.update_data(
        session_messages=[message.message_id],
        prompt_ids=[],
        temp_message_ids=[],
        submission_nav_stack=[],
        start_from_menu=True,
    )
    await send_submission_prompt(message, state, "title")


# saves the event title
# process title
@router.message(EventSubmission.title, F.text)
async def process_title(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return

    text = sanitize_text(message.text)
    if not text:
        msg = await message.answer("Please provide a valid title.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # keep titles short for dashboard buttons
    if len(text) > 100:
        msg = await message.answer(
            "Title is too long. Please keep it under 100 characters."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, f"📝 **Title:** {text}"
    )
    await record_nav_answer(state, message.message_id)

    # store the title and ask for description
    await state.update_data(
        title=text, last_step_user_message_id=message.message_id
    )
    await track_messages(state, message.message_id)
    await send_submission_prompt(message, state, "description")


# saves the event description
# process description
@router.message(EventSubmission.description, F.text)
async def process_description(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    text = sanitize_text(message.text)
    if not text:
        msg = await message.answer("Please provide a valid description.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # keep descriptions within telegram message limits
    if len(text) > 1000:
        msg = await message.answer(
            "Description is too long. Please keep it under 1000 characters."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, "✓ **Description received.**"
    )
    await record_nav_answer(state, message.message_id)

    # store the description and ask for date
    await state.update_data(
        description=text, last_step_user_message_id=message.message_id
    )
    await track_messages(state, message.message_id)
    await send_submission_prompt(message, state, "date")


# saves the event date
# process date
@router.message(EventSubmission.date, F.text)
async def process_date(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    event_date = parse_event_date_input(message.text)
    if event_date is None:
        msg = await message.answer(
            "Invalid date. Use DD MM YYYY, for example 22 11 2026."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    from zoneinfo import ZoneInfo
    from app.config import get_settings

    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    today = datetime.now(tz).date()

    # reject dates outside the allowed planning window
    if event_date < today:
        msg = await message.answer("Date cannot be in the past. Use DD MM YYYY.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    from datetime import timedelta

    if event_date > today + timedelta(days=365):
        msg = await message.answer("Date cannot be more than 1 year in the future.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, f"📅 **Date:** {event_date.strftime('%d.%m.%Y')}"
    )
    await record_nav_answer(state, message.message_id)
    await state.update_data(
        event_date=event_date, last_step_user_message_id=message.message_id
    )
    await track_messages(state, message.message_id)

    # ask for the start time after date validation
    await send_submission_prompt(message, state, "time")


# saves the event time
# process time
@router.message(EventSubmission.time, F.text)
async def process_time(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    event_time = parse_event_time_input(message.text)
    if event_time is None:
        msg = await message.answer("Invalid time. Use HH MM, for example 18 30.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

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
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # save the accepted time
    await finalize_previous_step(
        state, bot, message.chat.id, f"🕒 **Time:** {event_time.strftime('%H:%M')}"
    )
    await record_nav_answer(state, message.message_id)
    await state.update_data(
        event_time=event_time, last_step_user_message_id=message.message_id
    )
    await track_messages(state, message.message_id)

    # ask for the location after time validation
    await send_submission_prompt(message, state, "location")


# saves the event location
# process location
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

    text = sanitize_text(message.text)
    if not text:
        msg = await message.answer("Please provide a valid location.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # keep locations short for previews and dashboards
    if len(text) > 100:
        msg = await message.answer(
            "Location is too long. Please keep it under 100 characters."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, f"📍 **Location:** {text}"
    )
    await record_nav_answer(state, message.message_id)
    # store location and show categories
    await state.update_data(
        location=text, last_step_user_message_id=message.message_id
    )
    await track_messages(state, message.message_id)
    await send_submission_prompt(message, state, "category", session)


# saves the selected category
# process category
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
        msg = await message.answer(
            "Category not found. Please choose from the keyboard."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    # store category and ask for organizer
    await finalize_previous_step(
        state, bot, message.chat.id, f"📁 **Category:** {category.name}"
    )
    await record_nav_answer(state, message.message_id)

    await state.update_data(
        category_id=category.id,
        category_name=category.name,
        last_step_user_message_id=message.message_id,
    )
    await track_messages(state, message.message_id)
    await send_submission_prompt(message, state, "organizer")


# saves the organizer name
# process organizer
@router.message(EventSubmission.organizer, F.text)
async def process_organizer(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return

    text = sanitize_text(message.text)
    if not text:
        msg = await message.answer("Please provide a valid organizer name.")
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    if len(text) > 100:
        msg = await message.answer(
            "Organizer name is too long. Please keep it under 100 characters."
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await finalize_previous_step(
        state, bot, message.chat.id, f"🏢 **Organizer:** {text}"
    )
    await record_nav_answer(state, message.message_id)

    await state.update_data(
        organizer=text, last_step_user_message_id=message.message_id
    )
    await track_messages(state, message.message_id)
    await prompt_poster(message, state, bot)


async def validate_poster_image(message: Message, bot: Bot, file_id: str) -> bool:
    settings = get_settings()
    try:
        file = await bot.get_file(file_id)
        if file.file_size and file.file_size > settings.media_max_upload_bytes:
            raise ValueError("File too large")
        buffer = LimitedBytesIO(settings.media_max_upload_bytes)
        await bot.download_file(file.file_path, destination=buffer)
        process_image(
            buffer.getvalue(),
            max_px=800,
            max_size_bytes=settings.media_max_upload_bytes,
        )
        return True
    except ValueError:
        await message.answer(
            "Only JPEG, PNG, and WebP images under 5 MB are accepted. Please send a valid image."
        )
        return False
    except Exception:
        await message.answer(
            "Only JPEG, PNG, and WebP images under 5 MB are accepted. Please send a valid image."
        )
        return False


# saves the uploaded poster
# process poster
@router.message(EventSubmission.poster, F.photo)
async def process_poster(message: Message, state: FSMContext, bot: Bot):
    # use the highest resolution telegram photo
    file_id = message.photo[-1].file_id
    if not await validate_poster_image(message, bot, file_id):
        return
    await state.update_data(
        poster_file_id=file_id, last_step_user_message_id=message.message_id
    )
    await record_nav_answer(state, message.message_id)
    await track_messages(state, message.message_id)
    await finalize_previous_step(state, bot, message.chat.id, "🖼️ **Poster uploaded.**")
    await prompt_registration_link(message, state, bot)


# skips poster upload
# skip poster
@router.message(EventSubmission.poster, F.text == "Skip poster")
async def skip_poster(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await state.update_data(
        poster_file_id=None, last_step_user_message_id=message.message_id
    )
    await record_nav_answer(state, message.message_id)
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
    await push_nav_prompt(
        state,
        state_name=EventSubmission.poster.state,
        data_key="poster_file_id",
        prompt_id=msg.message_id,
    )
    await state.set_state(EventSubmission.poster)


# is valid url
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
    await push_nav_prompt(
        state,
        state_name=EventSubmission.registration_link.state,
        data_key="registration_url",
        prompt_id=msg.message_id,
    )
    await state.set_state(EventSubmission.registration_link)


# go back one step
async def go_back_one_step(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    data = await state.get_data()
    if data.get("submission_back_in_progress"):
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        return
    await state.update_data(submission_back_in_progress=True)
    try:
        await _go_back_one_step_locked(message, state, bot, session)
    finally:
        await state.update_data(submission_back_in_progress=False)


# go back one step locked
async def _go_back_one_step_locked(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    data = await state.get_data()
    stack = list(data.get("submission_nav_stack") or [])
    temp_ids = data.get("temp_message_ids", [])
    chat_id = message.chat.id

    await delete_messages_fast(bot, chat_id, reversed(temp_ids))

    if len(stack) < 2:
        await delete_messages_fast(
            bot,
            chat_id,
            [message.message_id, stack[-1].get("prompt_id") if stack else None],
        )
        await state.update_data(temp_message_ids=[])
        return

    current_entry = stack.pop()
    previous_entry = stack.pop()

    await delete_messages_fast(
        bot,
        chat_id,
        [
            message.message_id,
            current_entry.get("prompt_id"),
            previous_entry.get("answer_id"),
            previous_entry.get("prompt_id"),
        ],
    )

    previous_key = previous_entry.get("data_key")
    if previous_key:
        updates = {previous_key: None}
        if previous_key == "category_id":
            updates["category_name"] = None
        await state.update_data(**updates)

    await state.update_data(
        current_prompt_id=None,
        previous_prompt_id=None,
        prompt_ids=[],
        temp_message_ids=[],
        last_step_user_message_id=None,
        submission_nav_stack=stack,
    )

    previous_state = previous_entry.get("state")
    step_by_state = {
        EventSubmission.title.state: "title",
        EventSubmission.description.state: "description",
        EventSubmission.date.state: "date",
        EventSubmission.time.state: "time",
        EventSubmission.location.state: "location",
        EventSubmission.category.state: "category",
        EventSubmission.organizer.state: "organizer",
    }
    step = step_by_state.get(previous_state)
    if step:
        await send_submission_prompt(message, state, step, session)
        return
    if previous_state == EventSubmission.poster.state:
        await prompt_poster(message, state, bot)
        return
    if previous_state == EventSubmission.registration_link.state:
        await prompt_registration_link(message, state, bot)
        return


# back from poster
@router.message(EventSubmission.poster, F.text == "Back")
async def back_from_poster(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# back from registration
@router.message(EventSubmission.registration_link, F.text == "Back")
async def back_from_registration(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# back from preview
@router.message(EventSubmission.confirm, F.text == "Back")
async def back_from_preview(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# back from organizer
@router.message(EventSubmission.organizer, F.text == "Back")
async def back_from_organizer(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# back from category
@router.message(EventSubmission.category, F.text == "Back")
async def back_from_category(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# back from location
@router.message(EventSubmission.location, F.text == "Back")
async def back_from_location(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# back from time
@router.message(EventSubmission.time, F.text == "Back")
async def back_from_time(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# back from date
@router.message(EventSubmission.date, F.text == "Back")
async def back_from_date(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# back from description
@router.message(EventSubmission.description, F.text == "Back")
async def back_from_description(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    await go_back_one_step(message, state, bot, session)


# invalid poster input
@router.message(EventSubmission.poster)
async def invalid_poster_input(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
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
# process registration link
@router.message(EventSubmission.registration_link, F.text)
async def process_registration_link(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession
):
    if message.text == "Back to Menu":
        await cancel_submission_message(message, state, session)
        return
    if message.text == "Back":
        await go_back_one_step(message, state, bot, session)
        return
    if message.text == "Skip link":
        await skip_registration_link(message, state, bot)
        return

    if not is_valid_url(message.text) or len(message.text) > 2048:
        msg = await message.answer(
            "That doesn't look like a valid link or it is too long (max 2048 characters). Please send a full URL starting with http:// or https://, or click Skip link.",
            reply_markup=get_step_navigation_kb("Skip link"),
            parse_mode="Markdown",
        )
        await track_messages(state, message.message_id, msg.message_id, is_temp=True)
        return

    await state.update_data(
        registration_url=message.text, last_step_user_message_id=message.message_id
    )
    await record_nav_answer(state, message.message_id)
    await finalize_previous_step(
        state, bot, message.chat.id, f"🔗 **Link:** {message.text}"
    )
    await track_messages(state, message.message_id)
    await show_event_preview(message, state, bot)


# skips the registration link
async def skip_registration_link(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(
        registration_url=None, last_step_user_message_id=message.message_id
    )
    await record_nav_answer(state, message.message_id)
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
    safe_url = (
        html.escape(data["registration_url"]) if data.get("registration_url") else None
    )

    def render_preview(safe_desc: str) -> str:
        text = (
            f"<b>Event Preview</b>\n\n"
            f"<b>Title:</b> {safe_title}\n"
            f"<b>Date:</b> {data['event_date'].strftime('%d.%m.%Y')} at {data['event_time'].strftime('%H:%M')}\n"
            f"<b>Location:</b> {safe_location}\n"
            f"<b>Category:</b> {data['category_name']}\n"
            f"<b>Organizer:</b> {safe_organizer}\n\n"
            f"<b>Description:</b>\n{safe_desc}\n\n"
        )
        if safe_url:
            text += f"<b>Registration:</b> {safe_url}\n"
        return text

    safe_desc = (
        escape_and_fit_description(data["description"], render_preview)
        if data.get("poster_file_id")
        else html.escape(data["description"])
    )
    preview_text = render_preview(safe_desc)

    builder = get_confirm_kb()

    # telegram photo captions are limited to 1024 chars; long previews need text
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
    await push_nav_prompt(
        state,
        state_name=EventSubmission.confirm.state,
        data_key=None,
        prompt_id=msg.message_id,
    )
    await state.set_state(EventSubmission.confirm)


# creates the pending event after confirmation
# confirm submission
@router.message(EventSubmission.confirm, F.text == "Submit Event")
async def confirm_submission(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    data = await state.get_data()
    user = await upsert_user_from_telegram(session, message.from_user)

    # automatically compute a default end time (+1 hour)
    if "event_time" in data:
        event_time = data["event_time"]
        dummy_dt = datetime.combine(datetime.today(), event_time)
        data["event_end_time"] = (dummy_dt + timedelta(hours=1)).time()

    # save the event and show the user confirmation
    event = await create_pending_event(session, user, data)
    await session.commit()

    from app.handlers.start import get_main_menu_keyboard

    settings = get_settings()
    is_admin = user.telegram_id in settings.admin_ids

    await message.answer(
        "🎉 Your event has been submitted and is now pending moderation. You will be notified once it is approved!",
        reply_markup=get_main_menu_keyboard(is_admin),
    )

    await state.clear()


# cancels the submission flow via message or text button (fully deletes all intermediate chat history)
# cancel submission message
@router.message(EventSubmission.confirm, F.text == "Cancel")
async def cancel_submission_message(
    message: Message, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    messages = data.get("session_messages", [])

    # delete all interactive user responses and bot prompts from this submission session
    delete_ids = [*reversed(messages), message.message_id]

    # delete the previous welcome message to avoid duplicates
    from app.handlers.start import last_welcome_messages, send_main_menu

    welcome_msg_id = last_welcome_messages.get(message.from_user.id)
    if welcome_msg_id:
        delete_ids.append(welcome_msg_id)

    await delete_messages_fast(message.bot, message.chat.id, delete_ids)

    await state.clear()
    await send_main_menu(message, session)
