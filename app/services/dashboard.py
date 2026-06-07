from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, ChatCategorySetting, DashboardMessage
from app.models.event import Event, EventCategory
from app.services.event_cards import render_dashboard_event_line
from app.services.events import ensure_event_public_token
from app.services.telegram_delivery import call_with_telegram_backoff


from zoneinfo import ZoneInfo
from app.config import get_settings


# builds the dashboard message text for a chat
def render_dashboard(
    chat: Chat,
    enabled_categories: list[EventCategory],
    upcoming_events: list[Event],
    bot_username: str | None = None,
) -> str:
    lines = []

    if not upcoming_events:
        lines.append("No approved upcoming events.\n")
    else:
        # group events by relative date
        settings = get_settings()
        tz = ZoneInfo(settings.app_timezone)
        today = datetime.now(tz).date()

        grouped_events = {"Today": [], "Tomorrow": [], "This Week": [], "Later": []}

        for event in upcoming_events:
            days_diff = (event.event_date - today).days
            event_line = render_dashboard_event_line(
                event,
                bot_username=bot_username,
                include_date=days_diff > 1,
            )

            # place each event into its date group
            if days_diff == 0:
                grouped_events["Today"].append(event_line)
            elif days_diff == 1:
                grouped_events["Tomorrow"].append(event_line)
            elif 1 < days_diff <= 7:
                grouped_events["This Week"].append(event_line)
            else:
                grouped_events["Later"].append(event_line)

        for group_name, events in grouped_events.items():
            if events:
                lines.append(f"<b>{group_name}</b>")
                lines.extend(events)
                lines.append("")

    return "\n".join(lines)


# loads categories enabled for a chat
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


# finds the stored dashboard message for a chat
async def get_dashboard_message(
    session: AsyncSession,
    chat_id: int,
) -> DashboardMessage | None:
    result = await session.execute(
        select(DashboardMessage).where(DashboardMessage.chat_id == chat_id),
    )
    return result.scalar_one_or_none()


# creates or updates a chat dashboard message
async def create_or_update_dashboard_message(
    session: AsyncSession,
    bot: Bot,
    chat: Chat,
) -> DashboardMessage:
    from sqlalchemy.orm import selectinload
    from sqlalchemy import false

    if chat.chat_type == "private":
        raise ValueError("Dashboards are only sent to groups, supergroups, and channels.")

    enabled_categories = await get_enabled_categories(session, chat.id)
    enabled_cat_ids = [c.id for c in enabled_categories]

    from app.config import get_settings
    from zoneinfo import ZoneInfo

    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    today = datetime.now(tz).date()

    events_stmt = (
        select(Event)
        .where(
            Event.status == "approved",
            Event.event_date >= today,
            Event.category_id.in_(enabled_cat_ids) if enabled_cat_ids else false(),
        )
        .order_by(Event.event_date, Event.event_time)
        .options(selectinload(Event.detail_messages))
    )
    events_res = await session.execute(events_stmt)
    upcoming_events = events_res.scalars().all()
    for event in upcoming_events:
        ensure_event_public_token(event)
    await session.flush()

    bot_user = await bot.get_me()

    # render and hash the latest dashboard content
    text = render_dashboard(
        chat,
        enabled_categories,
        upcoming_events,
        bot_username=bot_user.username,
    )
    text_hash = sha256(text.encode("utf-8")).hexdigest()

    dashboard_message = await get_dashboard_message(session, chat.id)

    # create the message once or edit the existing one
    if dashboard_message is None:
        sent_message = await call_with_telegram_backoff(
            lambda: bot.send_message(
                chat_id=chat.telegram_chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            ),
            context=f"send dashboard to chat {chat.telegram_chat_id}",
        )
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

    await pin_dashboard_message_silently(bot, chat, dashboard_message.message_id)

    dashboard_message.last_rendered_at = datetime.now(UTC)
    dashboard_message.last_render_hash = text_hash
    await session.flush()
    return dashboard_message


# pin dashboard message silently
async def pin_dashboard_message_silently(
    bot: Bot,
    chat: Chat,
    message_id: int,
) -> None:
    try:
        await bot.pin_chat_message(
            chat_id=chat.telegram_chat_id,
            message_id=message_id,
            disable_notification=True,
        )
    except Exception:
        pass


# edits a dashboard message or recreates it when needed
async def edit_or_recreate_dashboard_message(
    bot: Bot,
    chat: Chat,
    dashboard_message: DashboardMessage,
    text: str,
) -> None:
    try:
        await call_with_telegram_backoff(
            lambda: bot.edit_message_text(
                chat_id=chat.telegram_chat_id,
                message_id=dashboard_message.message_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            ),
            context=f"edit dashboard in chat {chat.telegram_chat_id}",
        )
    except TelegramBadRequest as error:
        # ignore no-op edits from telegram
        message = str(error).lower()
        if "message is not modified" in message:
            return
        if (
            "message to edit not found" in message
            or "message can't be edited" in message
        ):
            sent_message = await call_with_telegram_backoff(
                lambda: bot.send_message(
                    chat_id=chat.telegram_chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                ),
                context=f"recreate dashboard in chat {chat.telegram_chat_id}",
            )
            dashboard_message.message_id = sent_message.message_id
            return
        raise
