from datetime import UTC, datetime

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import Chat as TelegramChat
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import EventAnalytics
from app.models.chat import Chat, ChatCategorySetting
from app.models.event import EventCategory
from app.services.telegram_delivery import is_bot_removed_error

REQUIRED_PERMISSION_KEYS = ("can_delete_messages", "can_edit_messages")
OPTIONAL_PERMISSION_KEYS = ("can_pin_messages",)
GROUP_CHAT_TYPES = {"group", "supergroup", "channel"}


def utcnow() -> datetime:
    return datetime.now(UTC)


# finds a registered chat by telegram id
async def get_chat_by_telegram_id(
    session: AsyncSession,
    telegram_chat_id: int,
) -> Chat | None:
    result = await session.execute(
        select(Chat).where(Chat.telegram_chat_id == telegram_chat_id),
    )
    return result.scalar_one_or_none()


async def delete_chat_by_id(session: AsyncSession, chat_id: int) -> None:
    chat = await session.get(Chat, chat_id)
    if chat is not None:
        await session.execute(
            delete(EventAnalytics).where(
                EventAnalytics.chat_id == chat.telegram_chat_id,
            )
        )
        await session.delete(chat)


async def mark_chat_inactive(session: AsyncSession, chat: Chat) -> None:
    chat.is_active = False
    chat.removed_at = utcnow()
    chat.registration_status = "inactive"
    await session.execute(
        delete(EventAnalytics).where(
            EventAnalytics.chat_id == chat.telegram_chat_id,
        )
    )


async def delete_chat_data(session: AsyncSession, chat: Chat) -> None:
    await session.execute(
        delete(EventAnalytics).where(
            EventAnalytics.chat_id == chat.telegram_chat_id,
        )
    )
    await session.delete(chat)


# creates or updates a telegram chat record
async def register_chat(
    session: AsyncSession,
    telegram_chat: TelegramChat,
    created_by_user_id: int | None,
    bot_id: int | None = None,
) -> Chat:
    chat = await get_chat_by_telegram_id(session, telegram_chat.id)

    # create the chat if it is not known yet
    if chat is None:
        chat = Chat(
            telegram_chat_id=telegram_chat.id,
            created_by_user_id=created_by_user_id,
            connected_at=utcnow(),
        )
        session.add(chat)

    # refresh chat metadata from telegram
    chat.title = telegram_chat.title
    chat.username = telegram_chat.username
    chat.chat_type = getattr(telegram_chat.type, "value", telegram_chat.type)
    chat.bot_id = bot_id
    chat.is_active = True
    if chat.connected_at is None:
        chat.connected_at = utcnow()
    chat.removed_at = None
    chat.last_activity_at = utcnow()

    await session.flush()
    await ensure_all_categories_enabled(session, chat)
    await session.flush()
    return chat


async def record_chat_activity(
    session: AsyncSession,
    telegram_chat: TelegramChat,
) -> Chat | None:
    chat_type = getattr(telegram_chat.type, "value", telegram_chat.type)
    if chat_type not in GROUP_CHAT_TYPES:
        return None

    chat = await get_chat_by_telegram_id(session, telegram_chat.id)
    if chat is None:
        return None

    chat.title = telegram_chat.title or chat.title
    chat.username = telegram_chat.username or chat.username
    chat.chat_type = chat_type
    chat.last_activity_at = utcnow()
    return chat


def permissions_from_chat_member(member, chat_type: str | None = None) -> dict:
    is_admin = member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
    can_edit_messages = bool(getattr(member, "can_edit_messages", False)) if is_admin else False
    if is_admin and chat_type in {"group", "supergroup"}:
        can_edit_messages = True
    permissions = {
        "can_delete_messages": bool(getattr(member, "can_delete_messages", False)) if is_admin else False,
        "can_edit_messages": can_edit_messages,
        "can_pin_messages": bool(getattr(member, "can_pin_messages", False)) if is_admin else False,
    }
    permissions["required_granted"] = all(
        permissions[key] for key in REQUIRED_PERMISSION_KEYS
    )
    permissions["optional_granted"] = all(
        permissions[key] for key in OPTIONAL_PERMISSION_KEYS
    )
    return permissions


def connected_group_status(chat: Chat) -> str:
    if not chat.is_active or chat.registration_status == "inactive":
        return "inactive"

    permissions = chat.permissions_status or {}
    if not all(bool(permissions.get(key)) for key in REQUIRED_PERMISSION_KEYS):
        return "missing_permissions"

    if chat.registration_status != "setup_complete" or not chat.categories_selected:
        return "setup_required"

    if chat.dashboard_message is None:
        return "setup_required"

    return "active"


async def sync_chat_telegram_metadata(
    session: AsyncSession,
    bot: Bot,
    chat: Chat,
    *,
    telegram_chat: TelegramChat | None = None,
) -> Chat:
    if telegram_chat is not None:
        chat.title = telegram_chat.title or chat.title
        chat.username = telegram_chat.username or chat.username
        chat.chat_type = getattr(telegram_chat.type, "value", telegram_chat.type)

    try:
        full_chat = await bot.get_chat(chat.telegram_chat_id)
        chat.title = full_chat.title or chat.title
        chat.username = full_chat.username or chat.username
        chat.chat_type = getattr(full_chat.type, "value", full_chat.type)
        invite_link = getattr(full_chat, "invite_link", None)
        if invite_link:
            chat.invite_link = invite_link
        elif chat.username:
            chat.invite_link = f"https://t.me/{chat.username}"
    except Exception:
        if chat.username:
            chat.invite_link = f"https://t.me/{chat.username}"

    try:
        chat.member_count = await bot.get_chat_member_count(chat.telegram_chat_id)
    except Exception:
        pass

    try:
        bot_member = await bot.get_chat_member(chat.telegram_chat_id, bot.id)
        chat.permissions_status = permissions_from_chat_member(bot_member, chat.chat_type)
        chat.is_active = bot_member.status not in {
            ChatMemberStatus.KICKED,
            ChatMemberStatus.LEFT,
        }
        if chat.is_active:
            chat.removed_at = None
            if chat.registration_status == "inactive":
                chat.registration_status = "pending_permissions"
        else:
            await delete_chat_data(session, chat)
            await session.flush()
            return chat
    except Exception as exc:
        if is_bot_removed_error(exc):
            await delete_chat_data(session, chat)
            await session.flush()
            return chat

    if chat.connected_at is None:
        chat.connected_at = chat.created_at or utcnow()

    await session.flush()
    return chat


# enables missing active categories for a chat
async def ensure_all_categories_enabled(session: AsyncSession, chat: Chat) -> None:
    # load active categories and existing settings
    categories = (
        (
            await session.execute(
                select(EventCategory).where(EventCategory.is_active.is_(True)),
            )
        )
        .scalars()
        .all()
    )

    existing_category_ids = set(
        (
            await session.execute(
                select(ChatCategorySetting.category_id).where(
                    ChatCategorySetting.chat_id == chat.id,
                ),
            )
        )
        .scalars()
        .all(),
    )

    # add default settings for new categories
    for category in categories:
        if category.id not in existing_category_ids:
            session.add(
                ChatCategorySetting(
                    chat_id=chat.id,
                    category_id=category.id,
                    is_enabled=True,
                ),
            )


# loads category settings for a chat
async def get_chat_category_settings(
    session: AsyncSession,
    chat_id: int,
) -> list[ChatCategorySetting]:
    result = await session.execute(
        select(ChatCategorySetting)
        .where(ChatCategorySetting.chat_id == chat_id)
        .options(selectinload(ChatCategorySetting.category))
        .join(EventCategory)
        .order_by(EventCategory.sort_order, EventCategory.name)
    )
    return list(result.scalars().all())


# toggles a category setting for a chat
async def toggle_chat_category(
    session: AsyncSession,
    chat_id: int,
    category_id: int,
) -> bool:
    result = await session.execute(
        select(ChatCategorySetting).where(
            ChatCategorySetting.chat_id == chat_id,
            ChatCategorySetting.category_id == category_id,
        )
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.is_enabled = not setting.is_enabled
        return setting.is_enabled
    return False
