from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.users import upsert_user_from_telegram

router = Router(name="start")


@router.message(CommandStart(), F.chat.type == "private")
async def handle_start(message: Message, session: AsyncSession) -> None:
    user = await upsert_user_from_telegram(session, message.from_user)
    settings = get_settings()
    is_admin = user.telegram_id in settings.admin_ids

    await message.answer(
        "👋 **Welcome to the Student Events Bot!**\n\n"
        "I am here to help you stay updated with university life without the noise.\n\n"
        "Use the menu below to explore events or manage your own submissions.",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown",
    )


def get_main_menu_keyboard(is_admin: bool = False):
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Create Event", callback_data="menu_create")
    builder.button(text="📅 My Events", callback_data="my_events")
    builder.button(text="⭐ Favorites", callback_data="menu_favorites")
    builder.button(text="🗓 Calendar", callback_data="menu_calendar")
    builder.button(text="🏷 Categories", callback_data="menu_categories")

    if is_admin:
        builder.button(text="🛠 Admin Panel", callback_data="admin_panel")

    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()
