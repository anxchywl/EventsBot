from __future__ import annotations

import html
from datetime import datetime

from aiogram.types import InlineKeyboardMarkup
from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings
from app.models.event import Event, EventCategory
from app.services.telegram_links import (
    build_event_deep_link,
    build_miniapp_event_url,
    build_public_miniapp_event_url,
    build_telegram_miniapp_direct_link,
    build_telegram_share_link,
)


def format_event_card_text(event: Event) -> str:
    title = html.escape(event.title)
    description = html.escape(event.description)
    location = html.escape(event.location)
    organizer = html.escape(event.organizer_name)
    category = html.escape(event.category.name)
    date_text = event.event_date.strftime("%b %d, %Y")
    time_text = event.event_time.strftime("%H:%M")

    return (
        f"<b>{title}</b>\n\n"
        f"{description}\n\n"
        f"<b>Date</b>: {date_text}\n"
        f"<b>Time</b>: {time_text}\n"
        f"<b>Location</b>: {location}\n"
        f"<b>Organizer</b>: {organizer}\n"
        f"<b>Category</b>: {category}"
    )


def build_event_page_keyboard(
    event: Event,
    *,
    bot_username: str | None = None,
    use_web_app: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    token = event.public_token
    miniapp_url = build_miniapp_event_url(
        miniapp_base_url=get_settings().miniapp_base_url,
        public_token=token,
    )

    if miniapp_url and use_web_app:
        builder.button(text="Open Event", web_app=WebAppInfo(url=miniapp_url))
    elif miniapp_url:
        builder.button(text="Open Event", url=miniapp_url)
    else:
        builder.button(text="Notify me before the event", callback_data=f"er_{token}")
        builder.button(text="Back to Events", callback_data="events_back")
        builder.button(text="Share Event", callback_data=f"es_{token}")

    if event.registration_url:
        builder.button(text="Open Link", url=event.registration_url)

    builder.adjust(1)
    return builder.as_markup()


def build_event_share_url(event: Event, *, bot_username: str | None) -> str | None:
    settings = get_settings()
    deep_link = build_telegram_miniapp_direct_link(
        bot_username=bot_username,
        miniapp_short_name=settings.telegram_miniapp_short_name,
        public_token=event.public_token,
    ) or build_public_miniapp_event_url(
        miniapp_base_url=settings.miniapp_base_url,
        public_token=event.public_token,
    ) or build_event_deep_link(
        bot_username=bot_username,
        public_token=event.public_token,
    )
    if not deep_link:
        return None

    return build_telegram_share_link(url=deep_link, text=event.title)


def render_dashboard_event_line(
    event: Event,
    *,
    bot_username: str | None,
    include_date: bool,
) -> str:
    settings = get_settings()
    event_link = build_telegram_miniapp_direct_link(
        bot_username=bot_username,
        miniapp_short_name=settings.telegram_miniapp_short_name,
        public_token=event.public_token,
    ) or build_public_miniapp_event_url(
        miniapp_base_url=settings.miniapp_base_url,
        public_token=event.public_token,
    ) or build_event_deep_link(
        bot_username=bot_username,
        public_token=event.public_token,
    )
    title = html.escape(event.title)
    location = html.escape(event.location)
    title_html = (
        f'<a href="{html.escape(event_link, quote=True)}">{title}</a>'
        if event_link
        else title
    )
    time_text = event.event_time.strftime("%H:%M")

    if include_date:
        date_text = event.event_date.strftime("%b %d")
        return f"- {date_text} {time_text} - {title_html}, {location}"

    return f"- {time_text} - {title_html}, {location}"


def render_private_events_list(
    events: list[Event],
    *,
    bot_username: str | None,
    categories: list[EventCategory] | None = None,
) -> str:
    if not events:
        return "<b>Events</b>\n\nNo approved upcoming events."

    lines = ["<b>Events</b>\n"]
    today = datetime.now().date()
    for event in events:
        include_date = event.event_date != today
        lines.append(
            render_dashboard_event_line(
                event,
                bot_username=bot_username,
                include_date=include_date,
            )
        )

    if categories:
        category_names = ", ".join(category.name for category in categories)
        lines.append(f"\n<b>Categories</b>\n{html.escape(category_names)}")

    return "\n".join(lines)
