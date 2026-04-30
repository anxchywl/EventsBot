from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chats import get_chat_by_telegram_id, register_chat
from app.services.dashboard import create_or_update_dashboard_message
from app.services.users import upsert_user_from_telegram

router = Router(name="admin_chat")


@router.message(Command("register_chat"))
async def handle_register_chat(
    message: Message,
    bot: Bot,
    session: AsyncSession,
) -> None:
    if not await can_manage_chat(message, bot):
        return

    user = await upsert_user_from_telegram(session, message.from_user)
    chat = await register_chat(
        session=session,
        telegram_chat=message.chat,
        created_by_user_id=user.id,
    )
    await session.commit()

    await message.answer(
        "Chat registered.\n\n"
        f"Telegram chat ID: <code>{chat.telegram_chat_id}</code>\n"
        "All default event categories are enabled for now.\n\n"
        "Run /dashboard to create or refresh the dashboard message."
    )


@router.message(Command("dashboard"))
async def handle_dashboard(
    message: Message,
    bot: Bot,
    session: AsyncSession,
) -> None:
    if not await can_manage_chat(message, bot):
        return

    user = await upsert_user_from_telegram(session, message.from_user)
    chat = await get_chat_by_telegram_id(session, message.chat.id)
    if chat is None:
        chat = await register_chat(
            session=session,
            telegram_chat=message.chat,
            created_by_user_id=user.id,
        )

    dashboard_message = await create_or_update_dashboard_message(
        session=session,
        bot=bot,
        chat=chat,
    )
    await session.commit()

    await message.answer(
        "Dashboard message is ready.\n\n"
        f"Dashboard message ID: <code>{dashboard_message.message_id}</code>"
    )


async def can_manage_chat(message: Message, bot: Bot) -> bool:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("This command must be used in a group or supergroup.")
        return False

    if message.from_user is None:
        await message.answer("Could not identify the command sender.")
        return False

    chat_member = await bot.get_chat_member(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )
    if chat_member.status not in {
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    }:
        await message.answer("Only chat admins can use this command.")
        return False

    return True
