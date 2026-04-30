from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import Chat, ChatCategorySetting
from app.models.event import Event, EventDetailMessage
from app.services.dashboard import create_or_update_dashboard_message


async def publish_approved_event(session: AsyncSession, bot: Bot, event: Event) -> None:
    # 1. Find target chats based on category
    stmt = (
        select(Chat)
        .join(ChatCategorySetting, ChatCategorySetting.chat_id == Chat.id)
        .where(
            ChatCategorySetting.category_id == event.category_id,
            ChatCategorySetting.is_enabled.is_(True),
        )
    )
    result = await session.execute(stmt)
    chats = result.scalars().all()

    for chat in chats:
        # 2 & 3. Create detailed event message and get message ID
        # Wait to check if a detail message already exists (if it was an edit)
        detail_stmt = select(EventDetailMessage).where(
            EventDetailMessage.event_id == event.id,
            EventDetailMessage.chat_id == chat.id,
        )
        detail_res = await session.execute(detail_stmt)
        detail_msg = detail_res.scalar_one_or_none()

        text = format_event_detail_text(event)
        keyboard = get_event_detail_keyboard(event)

        if detail_msg:
            # Edit existing detail message
            try:
                if event.poster_file_id:
                    # Editing caption/media is complex, simpler to edit caption if it was already a photo
                    await bot.edit_message_caption(
                        chat_id=chat.telegram_chat_id,
                        message_id=detail_msg.message_id,
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await bot.edit_message_text(
                        chat_id=chat.telegram_chat_id,
                        message_id=detail_msg.message_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
            except Exception:
                pass # Ignore if not modified
        else:
            # Send new detail message
            try:
                if event.poster_file_id:
                    msg = await bot.send_photo(
                        chat_id=chat.telegram_chat_id,
                        photo=event.poster_file_id,
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    msg = await bot.send_message(
                        chat_id=chat.telegram_chat_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )

                # 4. Create message link
                # Using the standard t.me/c format for supergroups
                clean_chat_id = str(chat.telegram_chat_id)
                if clean_chat_id.startswith("-100"):
                    clean_chat_id = clean_chat_id[4:]
                
                # We can construct a private link if it's a supergroup
                link = f"https://t.me/c/{clean_chat_id}/{msg.message_id}"
                
                new_detail = EventDetailMessage(
                    event_id=event.id,
                    chat_id=chat.id,
                    message_id=msg.message_id,
                    message_link=link,
                )
                session.add(new_detail)
            except Exception as e:
                print(f"Failed to send event detail to chat {chat.id}: {e}")
                continue

    await session.flush()

    # 5 & 6. Update dashboard messages
    for chat in chats:
        await create_or_update_dashboard_message(session, bot, chat)


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


def get_event_detail_keyboard(event: Event) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if event.registration_url:
        builder.button(text="🔗 Register", url=event.registration_url)
    # Future features (Stage 8): Remind me, Add to favorites
    builder.adjust(1)
    return builder.as_markup()
