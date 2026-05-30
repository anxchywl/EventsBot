import logging
from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chat import Chat
from app.services.chats import get_chat_by_telegram_id, register_chat
from app.services.dashboard import create_or_update_dashboard_message
from app.services.users import upsert_user_from_telegram

router = Router(name="admin_chat")
logger = logging.getLogger(__name__)


# registers the current group chat for dashboards
@router.message(Command("register_chat"))
async def handle_register_chat(
    message: Message,
    bot: Bot,
    session: AsyncSession,
) -> None:
    # allow only chat/bot admins to register chats
    if not await can_manage_chat(message, bot):
        return

    user = await upsert_user_from_telegram(session, message.from_user)
    chat = await register_chat(
        session=session,
        telegram_chat=message.chat,
        created_by_user_id=user.id,
    )
    await session.commit()

    sent_msg = await message.answer(
        f"✅ Chat registered. (ID: {chat.telegram_chat_id})\n\n"
        "Quick Setup:\n"
        "/categories - choose which event types to show here and create the dashboard\n\n"
        "Notes:\n"
        '• <i>Promote the bot to Admin (with "Delete Messages" right) so it can keep the chat clean and manage the dashboard.</i>\n'
        "• <i>If the dashboard message was deleted, just run /dashboard to recreate it.</i>\n"
        "• <i>This bot is <a href='https://github.com/anxchywl/events_bot'>open-source</a>.</i>",
        disable_web_page_preview=True,
    )
    chat.registration_message_id = sent_msg.message_id
    await session.commit()


# creates or refreshes the dashboard message
@router.message(Command("dashboard"))
async def handle_dashboard(
    message: Message,
    bot: Bot,
    session: AsyncSession,
) -> None:
    # allow only chat/bot admins to manage dashboards
    if not await can_manage_chat(message, bot):
        return

    # register the chat if this is the first dashboard command
    user = await upsert_user_from_telegram(session, message.from_user)
    chat = await get_chat_by_telegram_id(session, message.chat.id)
    if chat is None:
        chat = await register_chat(
            session=session,
            telegram_chat=message.chat,
            created_by_user_id=user.id,
        )

    # always trigger a refresh/recreation logic
    await create_or_update_dashboard_message(session=session, bot=bot, chat=chat)
    await session.commit()

    # wait a second so the user sees the dashboard appeared, then remove command
    import asyncio

    await asyncio.sleep(1)

    try:
        if message.chat.type != ChatType.PRIVATE:
            await bot.delete_message(
                chat_id=message.chat.id, message_id=message.message_id
            )
    except Exception as e:
        logger.warning(f"failed to delete dashboard command: {e}")


# handles the bot being removed from a chat
@router.my_chat_member(
    F.new_chat_member.status.in_({ChatMemberStatus.KICKED, ChatMemberStatus.LEFT})
)
async def handle_bot_removed(update: ChatMemberUpdated, session: AsyncSession) -> None:
    # only care about group chats
    if update.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return

    chat = await get_chat_by_telegram_id(session, update.chat.id)
    if chat is None:
        return

    # hard delete the chat row — cascades to category settings and dashboard message
    await session.delete(chat)
    await session.commit()
    logger.info(
        "bot removed from chat %s (%d) — chat data deleted",
        update.chat.title,
        update.chat.id,
    )


# checks whether the sender can manage the chat
async def can_manage_chat(message: Message, bot: Bot) -> bool:
    # rejects anonymous or missing senders
    if message.from_user is None:
        return False

    # allow bot global admins
    settings = get_settings()
    if message.from_user.id in settings.admin_ids:
        return True

    # check chat administrators in groups
    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        try:
            chat_member = await bot.get_chat_member(
                chat_id=message.chat.id,
                user_id=message.from_user.id,
            )
            if chat_member.status in {
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR,
                "owner",
            }:
                return True
        except Exception as e:
            logger.warning(f"failed to check chat admin status: {e}")

    # deny all others and notify
    await message.answer(
        "Only chat admins or bot administrators can use this command."
    )
    return False
