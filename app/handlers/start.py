from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.users import upsert_user_from_telegram

router = Router(name="start")


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


async def send_main_menu(message: Message, session: AsyncSession) -> None:
    user = await upsert_user_from_telegram(session, message.from_user)
    settings = get_settings()
    is_admin = user.telegram_id in settings.admin_ids

    # send the main menu with admin controls when allowed
    await message.answer(
        "👋 **Welcome to the Student Events Bot!**\n\n"
        "I am here to help you stay updated with university life without the noise.\n\n"
        "Use the menu below to explore events or manage your own submissions.",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown",
    )


# returns the user to the main menu
@router.callback_query(F.data == "start_menu")
async def process_start_menu(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    """
    returns the user to the main menu by editing the current message.
    """
    await state.clear()
    user = await upsert_user_from_telegram(session, callback.from_user)
    settings = get_settings()
    is_admin = user.telegram_id in settings.admin_ids

    # reuse the same menu text and keyboard
    await callback.message.edit_text(
        "👋 **Welcome to the Student Events Bot!**\n\n"
        "I am here to help you stay updated with university life without the noise.\n\n"
        "Use the menu below to explore events or manage your own submissions.",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown",
    )
    await callback.answer()


# builds the private main menu keyboard
def get_main_menu_keyboard(is_admin: bool = False):
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Create Event", callback_data="menu_create")
    builder.button(text="📅 My Events", callback_data="my_events")
    builder.button(text="⭐ Favorites", callback_data="menu_favorites")
    builder.button(text="🗓 Calendar", callback_data="menu_calendar")

    if is_admin:
        builder.button(text="🛠 Admin Panel", callback_data="admin_panel")

    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()
