from aiogram.types import Chat as TelegramChat
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, ChatCategorySetting
from app.models.event import EventCategory


async def get_chat_by_telegram_id(
    session: AsyncSession,
    telegram_chat_id: int,
) -> Chat | None:
    result = await session.execute(
        select(Chat).where(Chat.telegram_chat_id == telegram_chat_id),
    )
    return result.scalar_one_or_none()


async def register_chat(
    session: AsyncSession,
    telegram_chat: TelegramChat,
    created_by_user_id: int | None,
) -> Chat:
    chat = await get_chat_by_telegram_id(session, telegram_chat.id)

    if chat is None:
        chat = Chat(
            telegram_chat_id=telegram_chat.id,
            created_by_user_id=created_by_user_id,
        )
        session.add(chat)

    chat.title = telegram_chat.title
    chat.username = telegram_chat.username
    chat.chat_type = getattr(telegram_chat.type, "value", telegram_chat.type)
    chat.is_active = True

    await session.flush()
    await ensure_all_categories_enabled(session, chat)
    await session.flush()
    return chat


async def ensure_all_categories_enabled(session: AsyncSession, chat: Chat) -> None:
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

    for category in categories:
        if category.id not in existing_category_ids:
            session.add(
                ChatCategorySetting(
                    chat_id=chat.id,
                    category_id=category.id,
                    is_enabled=True,
                ),
            )
