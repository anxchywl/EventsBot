from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, ChatCategorySetting, DashboardMessage
from app.models.event import EventCategory


def render_placeholder_dashboard(chat: Chat, enabled_categories: list[EventCategory]) -> str:
    categories_text = ", ".join(category.name for category in enabled_categories)
    if not categories_text:
        categories_text = "No categories enabled yet"

    return (
        "<b>University Events Dashboard</b>\n\n"
        "No approved events yet.\n\n"
        "<b>Enabled categories</b>\n"
        f"{categories_text}\n\n"
        "<i>This message will be edited automatically when events are approved.</i>"
    )


async def get_enabled_categories(
    session: AsyncSession,
    chat_id: int,
) -> list[EventCategory]:
    result = await session.execute(
        select(EventCategory)
        .join(ChatCategorySetting, ChatCategorySetting.category_id == EventCategory.id)
        .where(
            ChatCategorySetting.chat_id == chat_id,
            ChatCategorySetting.is_enabled.is_(True),
            EventCategory.is_active.is_(True),
        )
        .order_by(EventCategory.sort_order, EventCategory.name),
    )
    return list(result.scalars().all())


async def get_dashboard_message(
    session: AsyncSession,
    chat_id: int,
) -> DashboardMessage | None:
    result = await session.execute(
        select(DashboardMessage).where(DashboardMessage.chat_id == chat_id),
    )
    return result.scalar_one_or_none()


async def create_or_update_dashboard_message(
    session: AsyncSession,
    bot: Bot,
    chat: Chat,
) -> DashboardMessage:
    enabled_categories = await get_enabled_categories(session, chat.id)
    text = render_placeholder_dashboard(chat, enabled_categories)
    text_hash = sha256(text.encode("utf-8")).hexdigest()

    dashboard_message = await get_dashboard_message(session, chat.id)

    if dashboard_message is None:
        sent_message = await bot.send_message(chat_id=chat.telegram_chat_id, text=text)
        dashboard_message = DashboardMessage(
            chat_id=chat.id,
            message_id=sent_message.message_id,
        )
        session.add(dashboard_message)
    else:
        await edit_or_recreate_dashboard_message(
            bot=bot,
            chat=chat,
            dashboard_message=dashboard_message,
            text=text,
        )

    dashboard_message.last_rendered_at = datetime.now(UTC)
    dashboard_message.last_render_hash = text_hash
    await session.flush()
    return dashboard_message


async def edit_or_recreate_dashboard_message(
    bot: Bot,
    chat: Chat,
    dashboard_message: DashboardMessage,
    text: str,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat.telegram_chat_id,
            message_id=dashboard_message.message_id,
            text=text,
        )
    except TelegramBadRequest as error:
        message = str(error).lower()
        if "message is not modified" in message:
            return
        if "message to edit not found" in message or "message can't be edited" in message:
            sent_message = await bot.send_message(chat_id=chat.telegram_chat_id, text=text)
            dashboard_message.message_id = sent_message.message_id
            return
        raise
