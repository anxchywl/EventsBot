from aiogram.types import Chat as TelegramChat
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, ChatCategorySetting
from app.models.event import EventCategory


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
    await session.execute(delete(Chat).where(Chat.id == chat_id))


# creates or updates a telegram chat record
async def register_chat(
    session: AsyncSession,
    telegram_chat: TelegramChat,
    created_by_user_id: int | None,
) -> Chat:
    chat = await get_chat_by_telegram_id(session, telegram_chat.id)

    # create the chat if it is not known yet
    if chat is None:
        chat = Chat(
            telegram_chat_id=telegram_chat.id,
            created_by_user_id=created_by_user_id,
        )
        session.add(chat)

    # refresh chat metadata from telegram
    chat.title = telegram_chat.title
    chat.username = telegram_chat.username
    chat.chat_type = getattr(telegram_chat.type, "value", telegram_chat.type)
    chat.is_active = True

    await session.flush()
    await ensure_all_categories_enabled(session, chat)
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
