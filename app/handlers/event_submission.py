from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.events import create_pending_event, get_active_categories, get_category_by_id
from app.services.users import upsert_user_from_telegram

router = Router()


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


@router.message(Command("submit_event"), F.chat.type == "private")
async def cmd_submit_event(message: Message, state: FSMContext, session: AsyncSession):
    categories = await get_active_categories(session)
    if not categories:
        await message.answer("No categories available. Please contact an administrator.")
        return

    await state.clear()
    await message.answer("Let's create a new event! What is the **title** of the event?", parse_mode="Markdown")
    await state.set_state(EventSubmission.title)


@router.message(EventSubmission.title, F.text)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Great! Now send me a **description** of the event.", parse_mode="Markdown")
    await state.set_state(EventSubmission.description)


@router.message(EventSubmission.description, F.text)
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("When will the event take place? Please send the **date** in YYYY-MM-DD format (e.g., 2023-12-31).", parse_mode="Markdown")
    await state.set_state(EventSubmission.date)


@router.message(EventSubmission.date, F.text)
async def process_date(message: Message, state: FSMContext):
    try:
        event_date = datetime.strptime(message.text, "%Y-%m-%d").date()
        await state.update_data(event_date=event_date)
    except ValueError:
        await message.answer("Invalid date format. Please use YYYY-MM-DD (e.g., 2023-12-31).")
        return

    await message.answer("What time will it start? Please send the **time** in HH:MM format (e.g., 18:30).", parse_mode="Markdown")
    await state.set_state(EventSubmission.time)


@router.message(EventSubmission.time, F.text)
async def process_time(message: Message, state: FSMContext):
    try:
        event_time = datetime.strptime(message.text, "%H:%M").time()
        await state.update_data(event_time=event_time)
    except ValueError:
        await message.answer("Invalid time format. Please use HH:MM (e.g., 18:30).")
        return

    await message.answer("Where will the event be held? Please provide the **location**.", parse_mode="Markdown")
    await state.set_state(EventSubmission.location)


@router.message(EventSubmission.location, F.text)
async def process_location(message: Message, state: FSMContext, session: AsyncSession):
    await state.update_data(location=message.text)
    
    categories = await get_active_categories(session)
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"cat_{cat.id}")
    builder.adjust(2)
    
    await message.answer("Please choose a **category** for your event:", reply_markup=builder.as_markup(), parse_mode="Markdown")
    await state.set_state(EventSubmission.category)


@router.callback_query(EventSubmission.category, F.data.startswith("cat_"))
async def process_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    category_id = int(callback.data.split("_")[1])
    category = await get_category_by_id(session, category_id)
    if not category:
        await callback.answer("Category not found.", show_alert=True)
        return
        
    await state.update_data(category_id=category.id, category_name=category.name)
    await callback.message.edit_text(f"Selected category: {category.name}")
    await callback.message.answer("Who is organizing the event? Send the **organizer or club name**.", parse_mode="Markdown")
    await state.set_state(EventSubmission.organizer)
    await callback.answer()


@router.message(EventSubmission.organizer, F.text)
async def process_organizer(message: Message, state: FSMContext):
    await state.update_data(organizer=message.text)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Skip poster", callback_data="skip_poster")
    
    await message.answer("Please send a **poster or image** for the event. If you don't have one, click Skip.", reply_markup=builder.as_markup(), parse_mode="Markdown")
    await state.set_state(EventSubmission.poster)


@router.message(EventSubmission.poster, F.photo)
async def process_poster(message: Message, state: FSMContext):
    # Store the highest resolution photo file_id
    file_id = message.photo[-1].file_id
    await state.update_data(poster_file_id=file_id)
    await prompt_registration_link(message, state)


@router.callback_query(EventSubmission.poster, F.data == "skip_poster")
async def skip_poster(callback: CallbackQuery, state: FSMContext):
    await state.update_data(poster_file_id=None)
    await callback.message.edit_text("Skipped poster.")
    await prompt_registration_link(callback.message, state)
    await callback.answer()


async def prompt_registration_link(message_obj: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="Skip link", callback_data="skip_link")
    await message_obj.answer("If there is a **registration link**, please send it now. Otherwise, click Skip.", reply_markup=builder.as_markup(), parse_mode="Markdown")
    await state.set_state(EventSubmission.registration_link)


@router.message(EventSubmission.registration_link, F.text)
async def process_registration_link(message: Message, state: FSMContext):
    await state.update_data(registration_url=message.text)
    await show_event_preview(message, state)


@router.callback_query(EventSubmission.registration_link, F.data == "skip_link")
async def skip_registration_link(callback: CallbackQuery, state: FSMContext):
    await state.update_data(registration_url=None)
    await callback.message.edit_text("Skipped registration link.")
    await show_event_preview(callback.message, state)
    await callback.answer()


async def show_event_preview(message_obj: Message, state: FSMContext):
    data = await state.get_data()
    
    preview_text = (
        f"📋 **Event Preview:**\n\n"
        f"**Title:** {data['title']}\n"
        f"**Date:** {data['event_date']} at {data['event_time']}\n"
        f"**Location:** {data['location']}\n"
        f"**Category:** {data['category_name']}\n"
        f"**Organizer:** {data['organizer']}\n\n"
        f"**Description:**\n{data['description']}\n\n"
    )
    if data.get("registration_url"):
        preview_text += f"**Registration:** {data['registration_url']}\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Submit Event", callback_data="submit_confirm")
    builder.button(text="❌ Cancel", callback_data="submit_cancel")
    builder.adjust(2)

    if data.get("poster_file_id"):
        await message_obj.answer_photo(
            data["poster_file_id"], 
            caption=preview_text, 
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )
    else:
        await message_obj.answer(
            preview_text, 
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )
    
    await state.set_state(EventSubmission.confirm)


@router.callback_query(EventSubmission.confirm, F.data == "submit_confirm")
async def confirm_submission(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    user = await upsert_user_from_telegram(session, callback.from_user)
    
    event = await create_pending_event(session, user, data)
    await session.commit()
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("🎉 Your event has been submitted and is now pending moderation. You will be notified once it is approved!")
    
    # Notify moderators
    settings = get_settings()
    # If there's no MODERATOR_CHAT_ID yet, we just print a log or skip. 
    # For Stage 4, let's assume we log it. Stage 5 will implement the actual moderator panel.
    # To prevent errors if the env var isn't set, we can check for it.
    moderator_chat_id = getattr(settings, "moderator_chat_id", None)
    if moderator_chat_id:
        from app.handlers.moderation import get_moderation_keyboard
        try:
            text = (
                f"🔔 **New Event Submitted**\n\n"
                f"**Title:** {event.title}\n"
                f"**Creator:** {user.first_name} (@{user.username})\n"
                f"**ID:** {event.id}"
            )
            if event.poster_file_id:
                await bot.send_photo(
                    moderator_chat_id, 
                    event.poster_file_id, 
                    caption=text, 
                    reply_markup=get_moderation_keyboard(event.id),
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    moderator_chat_id, 
                    text, 
                    reply_markup=get_moderation_keyboard(event.id),
                    parse_mode="Markdown"
                )
        except Exception:
            pass
            
    await state.clear()
    await callback.answer()


@router.callback_query(EventSubmission.confirm, F.data == "submit_cancel")
async def cancel_submission(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Submission cancelled.")
    await state.clear()
    await callback.answer()
