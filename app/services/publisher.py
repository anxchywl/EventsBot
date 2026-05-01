import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, ChatCategorySetting
from app.models.event import Event, EventDetailMessage

logger = logging.getLogger(__name__)


# publishes an approved event to all matching chats
async def publish_approved_event(session: AsyncSession, bot: Bot, event: Event) -> None:
    logger.info(f"publishing event {event.id} to category {event.category_id}")

    stmt = (
        select(Chat)
        .join(ChatCategorySetting, ChatCategorySetting.chat_id == Chat.id)
        .where(
            ChatCategorySetting.category_id == event.category_id,
            ChatCategorySetting.is_enabled.is_(True),
            Chat.is_active.is_(True),
        )
        .distinct()
    )
    result = await session.execute(stmt)
    chats = result.scalars().all()
    logger.info(f"found {len(chats)} chats for publishing")

    affected_chat_ids: set[int] = set()

    # create or refresh detail messages in each chat
    for chat in chats:
        # cache scalar values immediately — avoids lazy loads in error handlers
        chat_id = chat.id
        telegram_chat_id = chat.telegram_chat_id
        chat_username = chat.username

        detail_stmt = select(EventDetailMessage).where(
            EventDetailMessage.event_id == event.id,
            EventDetailMessage.chat_id == chat_id,
        )
        detail_res = await session.execute(detail_stmt)
        detail_msg = detail_res.scalar_one_or_none()

        text = format_event_detail_text(event)
        keyboard = get_event_detail_keyboard(event)

        if detail_msg:
            try:
                if event.poster_file_id:
                    await bot.edit_message_caption(
                        chat_id=telegram_chat_id,
                        message_id=detail_msg.message_id,
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown",
                    )
                else:
                    await bot.edit_message_text(
                        chat_id=telegram_chat_id,
                        message_id=detail_msg.message_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown",
                    )
            except Exception:
                pass

            if chat_username:
                link = f"https://t.me/{chat_username}/{detail_msg.message_id}"
            else:
                clean = str(telegram_chat_id)
                if clean.startswith("-100"):
                    clean = clean[4:]
                elif clean.startswith("-"):
                    clean = clean[1:]
                link = f"https://t.me/c/{clean}/{detail_msg.message_id}"

            detail_msg.message_link = link

        else:
            try:
                if event.poster_file_id:
                    msg = await bot.send_photo(
                        chat_id=telegram_chat_id,
                        photo=event.poster_file_id,
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown",
                    )
                else:
                    msg = await bot.send_message(
                        chat_id=telegram_chat_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown",
                    )

                if chat_username:
                    link = f"https://t.me/{chat_username}/{msg.message_id}"
                else:
                    clean = str(telegram_chat_id)
                    if clean.startswith("-100"):
                        clean = clean[4:]
                    elif clean.startswith("-"):
                        clean = clean[1:]
                    link = f"https://t.me/c/{clean}/{msg.message_id}"

                session.add(
                    EventDetailMessage(
                        event_id=event.id,
                        chat_id=chat_id,
                        message_id=msg.message_id,
                        message_link=link,
                    )
                )

                # note: do NOT access event.detail_messages — it is not eagerly loaded
                # and would trigger a lazy async load, crashing the loop

            except Exception as e:
                logger.error(f"failed to send event detail to chat {chat_id}: {e}")
                continue

        affected_chat_ids.add(chat_id)

    await session.flush()

    # signal the dashboard bus to refresh affected chats (debounced, non-blocking)
    if affected_chat_ids:
        try:
            from app.services.dashboard_bus import get_bus

            get_bus().schedule_refresh(affected_chat_ids)
        except Exception:
            pass


# formats the event detail message body
def format_event_detail_text(event: Event) -> str:
    text = (
        f"🌟 **{event.title}**\n\n"
        f"📅 **Date:** {event.event_date}\n"
        f"⏰ **Time:** {event.event_time}\n"
        f"📍 **Location:** {event.location}\n"
        f"👥 **Organizer:** {event.organizer_name}\n"
        f"🏷 **Category:** {event.category.name}\n\n"
        f"📝 **Description:**\n{event.description}\n"
    )
    return text


# builds actions shown below event details
def get_event_detail_keyboard(event: Event) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if event.registration_url:
        builder.button(text="🔗 Register", url=event.registration_url)

    builder.button(text="⏰ Remind me", callback_data=f"remind_opt_{event.id}")
    builder.button(text="⭐ Add to favorites", callback_data=f"fav_{event.id}")

    builder.adjust(1)
    return builder.as_markup()
