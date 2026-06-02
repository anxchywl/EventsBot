from aiogram import Bot, F, Router
import html

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.events import (
    delete_event_completely,
    get_event_by_id,
    get_user_events,
)
from app.services.users import upsert_user_from_telegram
from app.services.telegram_links import build_event_deep_link
from app.services.event_cards import escape_and_fit_description, format_event_card_text
from app.handlers.start import cleanup_main_menu_warnings, get_main_menu_keyboard
from app.handlers.message_cleanup import delete_messages_fast
from app.config import get_settings

router = Router()


# opens the current user's events list via callback
@router.callback_query(F.data == "my_events")
@router.callback_query(F.data == "my_events_back")
async def process_my_events(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await show_my_events(callback, session, state=state)


# opens the current user's events list via message
@router.message(F.text == "My Events", F.chat.type == "private")
async def process_my_events_message(message: Message, session: AsyncSession, state: FSMContext):
    await cleanup_main_menu_warnings(message, state)
    await show_my_events(message, session, state=state, answer=False, cmd_msg_id=message.message_id)


# renders events created by the current user
async def show_my_events(
    event_obj: Message | CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    *,
    answer: bool = True,
    cmd_msg_id: int | None = None,
):
    is_callback = isinstance(event_obj, CallbackQuery)
    user_obj = event_obj.from_user
    msg_obj = event_obj.message if is_callback else event_obj
    data = await state.get_data()
    await delete_messages_fast(
        msg_obj.bot,
        msg_obj.chat.id,
        [
            data.get("manage_event_msg_id"),
            data.get("my_events_selection_msg_id"),
            data.get("my_events_choose_msg_id"),
            data.get("confirm_delete_msg_id"),
            data.get("delete_command_msg_id"),
        ],
    )

    user = await upsert_user_from_telegram(session, user_obj)
    events = await get_user_events(session, user.id)
    events = [e for e in events if e.status != "rejected"]

    if not events:
        settings = get_settings()
        is_admin = user.telegram_id in settings.admin_ids

        text = (
            "**Your Events**\n\n"
            "You haven't created any events yet.\n\n"
            "Use the menu below to create one or explore other options."
        )
        sent = None
        if is_callback:
            sent = await msg_obj.edit_text(
                text,
                reply_markup=get_main_menu_keyboard(is_admin),
                parse_mode="Markdown",
            )
        else:
            sent = await msg_obj.answer(
                text,
                reply_markup=get_main_menu_keyboard(is_admin),
                parse_mode="Markdown",
            )
        current_data = await state.get_data()
        final_cmd_msg_id = cmd_msg_id if cmd_msg_id is not None else current_data.get("my_events_cmd_msg_id")
        await state.update_data(
            my_events_mode=False,
            my_events_event_map=None,
            my_events_cmd_msg_id=final_cmd_msg_id,
            my_events_choose_msg_id=sent.message_id if sent else None,
        )
        if is_callback and answer:
            await event_obj.answer()
        return

    event_map: dict[str, int] = {}
    event_buttons: list[str] = []
    for event in events:
        date_str = event.event_date.strftime("%B %d %Y")
        button_text = f"{event.title} ({date_str})"
        if button_text in event_map:
            button_text = f"{button_text} ({event.id})"
        event_map[button_text] = event.id
        event_buttons.append(button_text)

    keyboard_builder = ReplyKeyboardBuilder()
    for button_text in event_buttons:
        keyboard_builder.button(text=button_text)
    keyboard_builder.button(text="Back to Menu")
    keyboard_builder.adjust(1)

    header = "Choose the event"
    sent = None
    if is_callback:
        sent = await msg_obj.edit_text(
            header,
            reply_markup=keyboard_builder.as_markup(resize_keyboard=True),
            parse_mode="HTML",
        )
        if answer:
            await event_obj.answer()
    else:
        sent = await msg_obj.answer(
            header,
            reply_markup=keyboard_builder.as_markup(resize_keyboard=True),
            parse_mode="HTML",
        )

    current_data = await state.get_data()
    final_cmd_msg_id = cmd_msg_id if cmd_msg_id is not None else current_data.get("my_events_cmd_msg_id")

    await state.update_data(
        my_events_mode=True,
        my_events_event_map=event_map,
        manage_event_id=None,
        my_events_choose_msg_id=sent.message_id if sent else None,
        my_events_cmd_msg_id=final_cmd_msg_id,
    )


async def _delete_manage_temp_messages(state: FSMContext, bot: Bot, chat_id: int):
    data = await state.get_data()
    temp_ids = data.get("manage_temp_msg_ids") or []
    await delete_messages_fast(bot, chat_id, temp_ids)
    await state.update_data(manage_temp_msg_ids=[])


@router.message(F.text == "Edit", F.chat.type == "private")
async def process_manage_edit(
    message: Message, state: FSMContext, session: AsyncSession
):
    await _delete_manage_temp_messages(state, message.bot, message.chat.id)
    data = await state.get_data()
    event_id = data.get("manage_event_id")
    if not event_id:
        return

    from app.handlers.event_edit import start_edit_event

    await start_edit_event(
        message,
        state,
        session,
        event_id=event_id,
        use_reply_keyboard=True,
    )


@router.message(F.text == "Delete", F.chat.type == "private")
async def process_manage_delete(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    await _delete_manage_temp_messages(state, bot, message.chat.id)
    data = await state.get_data()
    event_id = data.get("manage_event_id")
    if not event_id:
        return

    builder = ReplyKeyboardBuilder()
    builder.button(text="Yes, Delete")
    builder.button(text="Cancel")
    builder.adjust(1)

    sent = await message.answer(
        "Are you sure you want to delete this event permanently?",
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode="Markdown",
    )
    await state.update_data(
        confirm_delete_event_id=event_id,
        delete_command_msg_id=message.message_id,
        confirm_delete_msg_id=sent.message_id,
    )


@router.message(F.text == "Yes, Delete", F.chat.type == "private")
async def process_confirm_delete_text(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    await _delete_manage_temp_messages(state, bot, message.chat.id)
    data = await state.get_data()
    event_id = data.get("confirm_delete_event_id")
    if not event_id:
        return

    success = await delete_event_completely(session, bot, event_id)
    if success:
        await session.commit()
        
        # Clean up delete-workflow messages
        msg_ids = [
            data.get("manage_event_msg_id"),
            data.get("delete_command_msg_id"),
            data.get("confirm_delete_msg_id"),
            message.message_id
        ]
        await delete_messages_fast(bot, message.chat.id, msg_ids)

        await message.answer("Event deleted successfully.")
        is_admin = data.get("is_admin_edit")
        await state.clear()
        if is_admin:
            from app.handlers.admin_panel import show_admin_active_events
            await show_admin_active_events(message, session, state, is_callback=False)
        else:
            await show_my_events(message, session, state=state, answer=False)
    else:
        await message.answer("Error deleting event or event not found.")


@router.message(F.text == "Cancel", F.chat.type == "private")
async def process_cancel_delete_text(
    message: Message, state: FSMContext, session: AsyncSession
):
    await _delete_manage_temp_messages(state, message.bot, message.chat.id)
    data = await state.get_data()
    if not data.get("confirm_delete_event_id"):
        return

    event_id = data.get("manage_event_id")
    if not event_id:
        return

    event = await get_event_by_id(session, event_id)
    if event:
        # Clean up delete-workflow and original event card messages
        msg_ids = [
            data.get("manage_event_msg_id"),
            data.get("delete_command_msg_id"),
            data.get("confirm_delete_msg_id"),
            message.message_id
        ]
        await delete_messages_fast(message.bot, message.chat.id, msg_ids)

        await state.update_data(confirm_delete_event_id=None)
        
        if data.get("is_admin_edit"):
            from app.handlers.admin_panel import _show_admin_manage_event
            await _show_admin_manage_event(message, session, state, event_id, is_callback=False)
        else:
            await send_manage_event_message(message, event, state=state, cleanup_previous=False)


@router.message(F.text == "Back to My Events", F.chat.type == "private")
async def process_back_to_my_events(
    message: Message, state: FSMContext, session: AsyncSession
):
    await _delete_manage_temp_messages(state, message.bot, message.chat.id)
    data = await state.get_data()
    
    # 1. Delete the event card message
    msg_id = data.get("manage_event_msg_id")
    
    # 2. Delete the user's event selection message
    selection_msg_id = data.get("my_events_selection_msg_id")

    # 3. Delete the original "Choose the event" message
    choose_msg_id = data.get("my_events_choose_msg_id")

    import logging
    logging.info(f"DEBUG BACK FULL DATA: {data}")
    logging.info(f"DEBUG BACK: msg_id={msg_id}, selection_msg_id={selection_msg_id}, choose_msg_id={choose_msg_id}")

    await delete_messages_fast(
        message.bot,
        message.chat.id,
        [msg_id, selection_msg_id, choose_msg_id, message.message_id],
    )

    await show_my_events(message, session, state=state, answer=False)


@router.message(F.text, ~F.text.in_(["Back to Menu", "Back to My Events", "Edit", "Delete", "Cancel", "Yes, Delete", "⚙️ Admin Panel", "Admin Panel"]), F.chat.type == "private")
async def process_my_events_selection(
    message: Message, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    if not data.get("my_events_mode"):
        if data.get("manage_event_id"):
            # User typed something wrong while viewing the event details page!
            sent = await message.answer("Please use the keyboard buttons below to manage the event. Direct messages are not supported here.")
            temp_ids = list(data.get("manage_temp_msg_ids", []))
            temp_ids.extend([message.message_id, sent.message_id])
            await state.update_data(manage_temp_msg_ids=temp_ids)
        return

    event_map = data.get("my_events_event_map") or {}
    event_id = event_map.get(message.text)
    if not event_id:
        # User typed something wrong while choosing the event!
        sent = await message.answer("Please choose an event from the keyboard list or click Back to Menu.")
        temp_ids = list(data.get("manage_temp_msg_ids", []))
        temp_ids.extend([message.message_id, sent.message_id])
        await state.update_data(manage_temp_msg_ids=temp_ids)
        return

    if message.text == "Back to Menu":
        return

    event = await get_event_by_id(session, event_id)
    if not event:
        await message.answer("Event not found.")
        return

    await _delete_manage_temp_messages(state, message.bot, message.chat.id)

    await state.update_data(
        my_events_mode=False,
        my_events_event_map=None,
        manage_event_id=event_id,
        my_events_selection_msg_id=message.message_id,
    )
    await send_manage_event_message(message, event, state=state)


async def send_manage_event_message(
    message: Message,
    event,
    state: FSMContext = None,
    *,
    cleanup_previous: bool = True,
):
    if state and cleanup_previous:
        data = await state.get_data()
        await delete_messages_fast(
            message.bot,
            message.chat.id,
            [
                data.get("manage_event_msg_id"),
                data.get("confirm_delete_msg_id"),
                data.get("delete_command_msg_id"),
            ],
        )

    safe_title = html.escape(event.title)
    safe_location = html.escape(event.location)
    safe_cat = html.escape(event.category.name)
    def render_text(safe_desc: str) -> str:
        return (
            f"<b>{safe_title}</b>\n\n"
            f"Date: {event.event_date}\n"
            f"Time: {event.event_time}\n"
            f"Location: {safe_location}\n"
            f"Category: {safe_cat}\n"
            f"Status: {event.status.upper()}\n\n"
            f"Description:\n{safe_desc}\n"
        )

    safe_desc = escape_and_fit_description(event.description, render_text) if event.poster_file_id else html.escape(event.description)
    text = render_text(safe_desc)

    builder = ReplyKeyboardBuilder()
    builder.button(text="Edit")
    builder.button(text="Delete")
    builder.button(text="Back to My Events")
    builder.adjust(1)
    reply_markup = builder.as_markup(resize_keyboard=True)

    if event.poster_file_id:
        sent = await message.answer_photo(
            event.poster_file_id,
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    else:
        sent = await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")

    if state:
        await state.update_data(manage_event_msg_id=sent.message_id)


# shows management actions for one user event
@router.callback_query(F.data.startswith("manage_event_"))
async def process_manage_event(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split("_")[2])
    event = await get_event_by_id(session, event_id)

    if not event:
        await callback.answer("Event not found.", show_alert=True)
        return

    # escape user content before rendering html
    safe_title = html.escape(event.title)
    safe_location = html.escape(event.location)
    safe_cat = html.escape(event.category.name)
    safe_desc = html.escape(event.description)

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

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )


# forwards edit requests to the edit flow
@router.callback_query(F.data.startswith("edit_event_"))
async def process_edit_event(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    from app.handlers.event_edit import start_edit_event

    await start_edit_event(callback, state, session)


# asks the user to confirm event deletion
@router.callback_query(F.data.startswith("delete_event_"))
async def process_delete_event(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[2])

    builder = InlineKeyboardBuilder()
    builder.button(text="❗ Yes, Delete", callback_data=f"confirm_delete_{event_id}")
    builder.button(text="Cancel", callback_data=f"manage_event_{event_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        "**Are you sure?**\n\nThis will permanently delete the event and all associated messages/reminders. This action cannot be undone.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


# deletes the event after confirmation
@router.callback_query(F.data.startswith("confirm_delete_"))
async def process_confirm_delete(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
):
    event_id = int(callback.data.split("_")[2])

    # remove database rows and telegram messages
    success = await delete_event_completely(session, bot, event_id)
    if success:
        await session.commit()
        await callback.answer("✅ Event deleted successfully.", show_alert=True)
        await show_my_events(callback, session, answer=False)
    else:
        await callback.answer(
            "❌ Error deleting event or event not found.", show_alert=True
        )


# shows favorite events from the main menu via callback
@router.callback_query(F.data == "menu_favorites")
async def process_menu_favorites(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
):
    await show_favorites(callback, session, bot)


# shows favorite events from the main menu via message
@router.message(F.text == "Favorites", F.chat.type == "private")
async def process_menu_favorites_message(
    message: Message, session: AsyncSession, bot: Bot
):
    await show_favorites(message, session, bot)


async def show_favorites(
    event_obj: Message | CallbackQuery, session: AsyncSession, bot: Bot
):
    from app.services.reminders import get_user_favorites

    is_callback = isinstance(event_obj, CallbackQuery)
    user_obj = event_obj.from_user
    msg_obj = event_obj.message if is_callback else event_obj

    user = await upsert_user_from_telegram(session, user_obj)
    favorites = await get_user_favorites(session, user)

    if not favorites:
        if is_callback:
            await event_obj.answer("You have no favorite events yet.", show_alert=True)
        else:
            await msg_obj.answer("You have no favorite events yet.")
        return

    lines = ["⭐ **Your Favorite Events**\n"]
    bot_user = await bot.get_me()
    # render favorites as event-page links when possible
    for event in favorites:
        detail_link = build_event_deep_link(
            bot_username=bot_user.username,
            public_token=event.public_token,
        )
        title = (
            f'<a href="{html.escape(detail_link, quote=True)}">{html.escape(event.title)}</a>'
            if detail_link
            else html.escape(event.title)
        )
        date_str = event.event_date.strftime("%b %d")
        lines.append(f"• {date_str} — {title}")

    builder = InlineKeyboardBuilder()
    builder.button(text="Back to Menu", callback_data="start_menu")

    if is_callback:
        await msg_obj.edit_text(
            "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML"
        )
        await event_obj.answer()
    else:
        await msg_obj.answer(
            "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML"
        )


# answers unfinished menu items
@router.callback_query(F.data == "menu_calendar")
async def process_menu_coming_soon(callback: CallbackQuery):
    await callback.answer("This feature is coming soon!", show_alert=True)


@router.message(F.text == "Calendar", F.chat.type == "private")
async def process_menu_coming_soon_message(message: Message):
    await message.answer("This feature is coming soon!")
