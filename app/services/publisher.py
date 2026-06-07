import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, ChatCategorySetting
from app.models.event import Event, EventDetailMessage
from app.services.chats import delete_chat_by_id
from app.services.event_cards import build_event_page_keyboard, format_event_card_text
from app.services.telegram_links import build_message_link
from app.services.telegram_delivery import (
    call_with_telegram_backoff,
    is_bot_removed_error,
    pause_between_telegram_deliveries,
)

logger = logging.getLogger(__name__)


# publish approved events to matching telegram chats
async def publish_approved_event(session: AsyncSession, bot: Bot, event: Event) -> None:
    logger.info(f"publishing event {event.id} to category {event.category_id}")

    stmt = (
        select(Chat)
        .join(ChatCategorySetting, ChatCategorySetting.chat_id == Chat.id)
        .where(
            ChatCategorySetting.category_id == event.category_id,
            ChatCategorySetting.is_enabled.is_(True),
            Chat.is_active.is_(True),
            Chat.chat_type != "private",
        )
        .distinct()
    )
    result = await session.execute(stmt)
    chats = result.scalars().all()
    logger.info(f"found {len(chats)} chats for publishing")

    bot_user = await bot.get_me()
    affected_chat_ids: set[int] = set()

    # pace telegram delivery while refreshing each chat detail message
    for chat in chats:
        # cache scalar values immediately avoids lazy loads in error handlers
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
        keyboard = get_event_detail_keyboard(event, bot_username=bot_user.username)

        if detail_msg:
            try:
                if event.poster_file_id:
                    await call_with_telegram_backoff(
                        lambda: bot.edit_message_caption(
                            chat_id=telegram_chat_id,
                            message_id=detail_msg.message_id,
                            caption=text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        ),
                        context=f"edit event {event.id} caption in chat {telegram_chat_id}",
                    )
                else:
                    await call_with_telegram_backoff(
                        lambda: bot.edit_message_text(
                            chat_id=telegram_chat_id,
                            message_id=detail_msg.message_id,
                            text=text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        ),
                        context=f"edit event {event.id} text in chat {telegram_chat_id}",
                    )
            except Exception as e:
                if is_bot_removed_error(e):
                    await delete_chat_by_id(session, chat_id)
                    logger.warning(
                        "removed chat %s after Telegram delivery failed: %s",
                        telegram_chat_id,
                        e,
                    )
                    continue
                logger.warning(
                    "failed to edit event detail in chat %s: %s",
                    telegram_chat_id,
                    e,
                )

            detail_msg.message_link = build_message_link(
                telegram_chat_id=telegram_chat_id,
                message_id=detail_msg.message_id,
                username=chat_username,
                chat_type=chat.chat_type,
            )

        else:
            try:
                if event.poster_file_id:
                    msg = await call_with_telegram_backoff(
                        lambda: bot.send_photo(
                            chat_id=telegram_chat_id,
                            photo=event.poster_file_id,
                            caption=text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        ),
                        context=f"send event {event.id} photo to chat {telegram_chat_id}",
                    )
                else:
                    msg = await call_with_telegram_backoff(
                        lambda: bot.send_message(
                            chat_id=telegram_chat_id,
                            text=text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        ),
                        context=f"send event {event.id} text to chat {telegram_chat_id}",
                    )

                session.add(
                    EventDetailMessage(
                        event_id=event.id,
                        chat_id=chat_id,
                        message_id=msg.message_id,
                        message_link=build_message_link(
                            telegram_chat_id=telegram_chat_id,
                            message_id=msg.message_id,
                            username=chat_username,
                            chat_type=chat.chat_type,
                        ),
                    )
                )

                # note: do not access event.detail_messages it is not eagerly loaded
                # and would trigger a lazy async load, crashing the loop

            except Exception as e:
                if is_bot_removed_error(e):
                    await delete_chat_by_id(session, chat_id)
                    logger.warning(
                        "removed chat %s after Telegram delivery failed: %s",
                        telegram_chat_id,
                        e,
                    )
                    continue

                logger.error(f"failed to send event detail to chat {chat_id}: {e}")
                continue

        affected_chat_ids.add(chat_id)
        await pause_between_telegram_deliveries()

    await session.flush()

    # refresh dashboards asynchronously after message delivery
    if affected_chat_ids:
        try:
            from app.services.dashboard_bus import get_bus

            get_bus().schedule_refresh(affected_chat_ids)
        except Exception:
            pass


# format event detail text for telegram html
def format_event_detail_text(event: Event) -> str:
    return format_event_card_text(event, caption_safe=bool(event.poster_file_id))


# build event detail actions for telegram users
def get_event_detail_keyboard(
    event: Event, *, bot_username: str | None = None
) -> InlineKeyboardMarkup:
    return build_event_page_keyboard(
        event,
        bot_username=bot_username,
        use_web_app=False,
        open_event_only=True,
    )
