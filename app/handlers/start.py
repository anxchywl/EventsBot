from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, MenuButtonWebApp, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.handlers.message_cleanup import delete_messages_fast
from app.services.users import upsert_user_from_telegram

router = Router(name="start")


# handles global back to menu message
@router.message(F.text == "Back to Menu", F.chat.type == "private")
async def handle_back_to_menu(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await _cleanup_menu_messages(message, state, extra_ids=[message.message_id])
    await state.clear()
    await send_main_menu(message, session)


# opens an event from dashboard deep links
@router.message(CommandStart(deep_link=True), F.chat.type == "private")
async def handle_event_deep_link(
    message: Message,
    command: CommandObject,
    bot: Bot,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()

    payload = command.args or ""
    if not payload.startswith("event_"):
        await send_main_menu(message, session)
        return

    from app.handlers.event_pages import send_event_page_from_token

    await send_event_page_from_token(
        message,
        session,
        bot,
        public_token=payload.removeprefix("event_"),
        source="deep_link",
    )


# handles the private start command
@router.message(CommandStart(), F.chat.type == "private")
async def handle_start(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await send_main_menu(message, session)


# tracks the last welcome message ID for each user so it can be cleanly replaced
last_welcome_messages = {}


async def send_main_menu(message: Message, session: AsyncSession) -> None:
    user = await upsert_user_from_telegram(session, message.from_user)
    settings = get_settings()
    is_admin = user.telegram_id in settings.admin_ids

    # Set chat menu button to default base Mini App url
    if settings.miniapp_base_url:
        try:
            await message.bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=MenuButtonWebApp(
                    text="Launch App",
                    web_app=WebAppInfo(url=settings.miniapp_base_url)
                )
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to set default chat menu button: {e}")

    # send the main menu with admin controls when allowed
    msg = await message.answer(
        "**Welcome to the Student Events Bot!**\n\n"
        "I am here to help you stay updated with university life without the noise.\n\n"
        "Use the menu below to explore events or manage your own submissions.",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown",
    )
    last_welcome_messages[user.telegram_id] = msg.message_id


# returns the user to the main menu
@router.callback_query(F.data == "start_menu")
async def process_start_menu(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    """
    Returns the user to the main menu by deleting active menu panels and resending the welcome menu.
    """
    user = await upsert_user_from_telegram(session, callback.from_user)
    settings = get_settings()
    is_admin = user.telegram_id in settings.admin_ids

    # Set chat menu button to default base Mini App url
    if settings.miniapp_base_url:
        try:
            await callback.bot.set_chat_menu_button(
                chat_id=callback.message.chat.id,
                menu_button=MenuButtonWebApp(
                    text="Launch App",
                    web_app=WebAppInfo(url=settings.miniapp_base_url)
                )
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to set default chat menu button: {e}")

    # delete the old welcome message and any stateful menu messages first
    await _cleanup_menu_messages(callback.message, state, extra_ids=[callback.message.message_id])
    await state.clear()

    await send_main_menu(callback.message, session)
    await callback.answer()


async def _cleanup_menu_messages(
    message: Message,
    state: FSMContext,
    *,
    extra_ids: list[int | None] | None = None,
) -> None:
    data = await state.get_data()
    user_id = message.from_user.id
    ids_to_delete = []

    old_welcome_id = last_welcome_messages.get(user_id)
    if old_welcome_id and old_welcome_id != message.message_id:
        ids_to_delete.append(old_welcome_id)
    last_welcome_messages.pop(user_id, None)

    my_events_cmd_msg_id = data.get("my_events_cmd_msg_id")
    my_events_choose_msg_id = data.get("my_events_choose_msg_id")
    my_events_selection_msg_id = data.get("my_events_selection_msg_id")
    manage_event_msg_id = data.get("manage_event_msg_id")
    confirm_delete_msg_id = data.get("confirm_delete_msg_id")
    delete_command_msg_id = data.get("delete_command_msg_id")
    if my_events_cmd_msg_id:
        ids_to_delete.append(my_events_cmd_msg_id)
    if my_events_choose_msg_id:
        ids_to_delete.append(my_events_choose_msg_id)
    if my_events_selection_msg_id:
        ids_to_delete.append(my_events_selection_msg_id)
    if manage_event_msg_id:
        ids_to_delete.append(manage_event_msg_id)
    if confirm_delete_msg_id:
        ids_to_delete.append(confirm_delete_msg_id)
    if delete_command_msg_id:
        ids_to_delete.append(delete_command_msg_id)

    manage_temp_ids = data.get("manage_temp_msg_ids") or []
    ids_to_delete.extend(manage_temp_ids)

    admin_panel_msg_id = data.get("admin_panel_msg_id")
    if admin_panel_msg_id:
        ids_to_delete.append(admin_panel_msg_id)

    admin_panel_user_msg_id = data.get("admin_panel_user_msg_id")
    if admin_panel_user_msg_id:
        ids_to_delete.append(admin_panel_user_msg_id)

    admin_msg_ids = data.get("admin_msg_ids") or []
    ids_to_delete.extend(admin_msg_ids)

    admin_temp_msg_ids = data.get("admin_temp_msg_ids") or []
    ids_to_delete.extend(admin_temp_msg_ids)

    messages = data.get("session_messages", [])
    ids_to_delete.extend(reversed(messages))
    if extra_ids:
        ids_to_delete.extend(extra_ids)
    await delete_messages_fast(message.bot, message.chat.id, ids_to_delete)


# builds the private main menu keyboard
def get_main_menu_keyboard(is_admin: bool = False):
    builder = ReplyKeyboardBuilder()
    builder.button(text="Create Event")
    builder.button(text="My Events")

    if is_admin:
        builder.button(text="Admin Panel")

    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
