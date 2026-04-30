from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import html

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, ChatCategorySetting, DashboardMessage
from app.models.event import Event, EventCategory


from zoneinfo import ZoneInfo
from app.config import get_settings


def render_dashboard(
    chat: Chat, enabled_categories: list[EventCategory], upcoming_events: list[Event]
) -> str:
    categories_text = ", ".join(category.name for category in enabled_categories)
    if not categories_text:
        categories_text = "No categories enabled yet"

    lines = ["<b>University Events Dashboard</b>\n"]

    if not upcoming_events:
        lines.append("No approved upcoming events.\n")
    else:
        settings = get_settings()
        tz = ZoneInfo(settings.app_timezone)
        today = datetime.now(tz).date()

        grouped_events = {"Today": [], "Tomorrow": [], "This Week": [], "Later": []}

        for event in upcoming_events:
            days_diff = (event.event_date - today).days

            # find the detail link for this chat
            detail_link = None
            for detail in event.detail_messages:
                if detail.chat_id == chat.id:
                    detail_link = detail.message_link
                    break

            escaped_title = html.escape(event.title)
            escaped_location = html.escape(event.location)

            event_title = (
                f'<a href="{detail_link}">{escaped_title}</a>'
                if detail_link
                else escaped_title
            )
            time_str = event.event_time.strftime("%H:%M")
            date_str = event.event_date.strftime("%b %d")

            event_line = f"• {time_str} — {event_title}, {escaped_location}"
            if days_diff > 1:
                event_line = (
                    f"• {date_str} {time_str} — {event_title}, {escaped_location}"
                )

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

    lines.append("<b>Enabled categories</b>")
    lines.append(f"{categories_text}\n")
    lines.append("<i>This message is updated automatically.</i>")

    return "\n".join(lines)


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
    from sqlalchemy.orm import selectinload
    from sqlalchemy import false

    enabled_categories = await get_enabled_categories(session, chat.id)
    enabled_cat_ids = [c.id for c in enabled_categories]

    from app.config import get_settings
    from zoneinfo import ZoneInfo

    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    today = datetime.now(tz).date()

    # fetch upcoming events for enabled categories (filter past events)
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

    # fix broken links in the database for upcoming events
    for event in upcoming_events:
        for detail in event.detail_messages:
            if detail.message_link and (
                "/c/-100" in detail.message_link or "/c/-" in detail.message_link
            ):
                # fetch the chat to get current username or id
                from app.models.chat import Chat

                chat_obj = await session.get(Chat, detail.chat_id)
                if chat_obj:
                    if chat_obj.username:
                        detail.message_link = (
                            f"https://t.me/{chat_obj.username}/{detail.message_id}"
                        )
                    else:
                        clean_chat_id = str(chat_obj.telegram_chat_id)
                        if clean_chat_id.startswith("-100"):
                            clean_chat_id = clean_chat_id[4:]
                        elif clean_chat_id.startswith("-"):
                            clean_chat_id = clean_chat_id[1:]
                        detail.message_link = (
                            f"https://t.me/c/{clean_chat_id}/{detail.message_id}"
                        )

    await session.flush()

    text = render_dashboard(chat, enabled_categories, upcoming_events)
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
        if (
            "message to edit not found" in message
            or "message can't be edited" in message
        ):
            sent_message = await bot.send_message(
                chat_id=chat.telegram_chat_id, text=text
            )
            dashboard_message.message_id = sent_message.message_id
            return
        raise
