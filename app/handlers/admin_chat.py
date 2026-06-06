import logging
from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chat import Chat
from app.services.chats import (
    delete_chat_data,
    get_chat_by_telegram_id,
    permissions_from_chat_member,
    record_chat_activity,
    register_chat,
    sync_chat_telegram_metadata,
)
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
    if message.chat.type == ChatType.PRIVATE:
        return

    # allow only chat/bot admins to register chats
    if not await can_manage_chat(message, bot):
        return

    user = await upsert_user_from_telegram(session, message.from_user)
    chat = await register_chat(
        session=session,
        telegram_chat=message.chat,
        created_by_user_id=user.id,
        bot_id=bot.id,
    )
    await sync_chat_telegram_metadata(session, bot, chat, telegram_chat=message.chat)
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
    chat.setup_message_id = sent_msg.message_id
    chat.registration_status = "setup_complete"
    chat.last_activity_at = chat.last_activity_at or chat.created_at
    await session.commit()


# creates or refreshes the dashboard message
@router.message(Command("dashboard"))
async def handle_dashboard(
    message: Message,
    bot: Bot,
    session: AsyncSession,
) -> None:
    if message.chat.type == ChatType.PRIVATE:
        return

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
            bot_id=bot.id,
        )

    # always trigger a refresh/recreation logic
    await sync_chat_telegram_metadata(session, bot, chat, telegram_chat=message.chat)
    await create_or_update_dashboard_message(session=session, bot=bot, chat=chat)
    chat.last_activity_at = chat.last_activity_at or chat.created_at
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
    if update.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}:
        return

    chat = await get_chat_by_telegram_id(session, update.chat.id)
    if chat is None:
        return

    await delete_chat_data(session, chat)
    await session.commit()
    logger.info(
        "bot removed from chat %s (%d) — chat data deleted",
        update.chat.title,
        update.chat.id,
    )


# handles bot added to group or permissions changed
@router.my_chat_member(
    F.new_chat_member.status.in_(
        {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.RESTRICTED}
    )
)
async def handle_bot_membership_update(
    update: ChatMemberUpdated, bot: Bot, session: AsyncSession
) -> None:
    if update.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}:
        return

    # Create user if needed
    user = None
    if update.from_user:
        user = await upsert_user_from_telegram(session, update.from_user)

    chat = await get_chat_by_telegram_id(session, update.chat.id)
    if chat is None:
        chat = await register_chat(
            session=session,
            telegram_chat=update.chat,
            created_by_user_id=user.id if user else None,
            bot_id=bot.id,
        )
        chat.registration_status = "pending_permissions"

    await sync_chat_telegram_metadata(session, bot, chat, telegram_chat=update.chat)

    chat_type = getattr(update.chat.type, "value", update.chat.type)
    permissions = permissions_from_chat_member(update.new_chat_member, chat_type)
    req_del = permissions["can_delete_messages"]
    req_edit = permissions["can_edit_messages"]
    req_pin = permissions["can_pin_messages"]

    del_icon = "✅" if req_del else "❌"
    edit_icon = "✅" if req_edit else "❌"
    pin_icon = "✅" if req_pin else "❌"

    chat.permissions_status = permissions

    if req_del and req_edit:
        setup_status = "Bot is ready to work."
    else:
        setup_status = "Waiting for permissions..."

    text = (
        f"<b>SETUP</b>\n\n"
        f"Please promote the bot to Admin and grant the required permissions.\n\n"
        f"Permissions\n"
        f"{del_icon} Delete Messages\n"
        f"{edit_icon} Edit Messages\n"
        f"{pin_icon} Pin Messages\n\n"
        f"{setup_status}"
    )

    if chat.setup_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat.telegram_chat_id,
                message_id=chat.setup_message_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.warning(f"Failed to edit setup message: {e}")
                # Send a new one if not found or other errors
                sent_msg = await bot.send_message(
                    chat_id=chat.telegram_chat_id,
                    text=text,
                    parse_mode="HTML",
                )
                chat.setup_message_id = sent_msg.message_id
    else:
        sent_msg = await bot.send_message(
            chat_id=chat.telegram_chat_id,
            text=text,
            parse_mode="HTML",
        )
        chat.setup_message_id = sent_msg.message_id

    await session.commit()

    if req_del and req_edit:
        import asyncio
        await asyncio.sleep(1)

        try:
            from app.handlers.categories import (
                load_category_selection,
                show_category_chooser_message,
            )

            categories, enabled_ids = await load_category_selection(session, chat.id)
            await show_category_chooser_message(
                bot=bot,
                chat_id=chat.telegram_chat_id,
                message_id=chat.setup_message_id,
                categories=categories,
                enabled_ids=enabled_ids,
            )
            chat.registration_status = "setup_complete"
            await session.commit()
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.warning(f"Failed to edit to category chooser: {e}")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_group_activity(message: Message, session: AsyncSession) -> None:
    await record_chat_activity(session, message.chat)
    await session.commit()


@router.channel_post()
async def handle_channel_activity(message: Message, session: AsyncSession) -> None:
    await record_chat_activity(session, message.chat)
    await session.commit()


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

    return False
