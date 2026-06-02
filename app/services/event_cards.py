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

PHOTO_CAPTION_LIMIT = 1024


def escape_and_fit_description(raw_description: str, render_text, *, limit: int = PHOTO_CAPTION_LIMIT) -> str:
    escaped_description = html.escape(raw_description or "")
    if len(render_text(escaped_description)) <= limit:
        return escaped_description

    suffix = "..."
    low = 0
    high = len(raw_description or "")
    best = suffix
    while low <= high:
        mid = (low + high) // 2
        candidate = html.escape((raw_description or "")[:mid]) + suffix
        if len(render_text(candidate)) <= limit:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best


def format_event_card_text(event: Event, *, caption_safe: bool = False) -> str:
    title = html.escape(event.title)
    location = html.escape(event.location)
    organizer = html.escape(event.organizer_name)
    category = html.escape(event.category.name)
    date_text = event.event_date.strftime("%b %d, %Y")
    time_text = event.event_time.strftime("%H:%M")

    def render_text(description: str) -> str:
        return (
            f"<b>{title}</b>\n\n"
            f"{description}\n\n"
            f"<b>Date</b>: {date_text}\n"
            f"<b>Time</b>: {time_text}\n"
            f"<b>Location</b>: {location}\n"
            f"<b>Organizer</b>: {organizer}\n"
            f"<b>Category</b>: {category}"
        )

    description = (
        escape_and_fit_description(event.description, render_text)
        if caption_safe
        else html.escape(event.description)
    )
    return render_text(description)


def build_event_page_keyboard(
    event: Event,
    *,
    bot_username: str | None = None,
    use_web_app: bool = False,
    open_event_only: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    token = event.public_token
    settings = get_settings()
    miniapp_url = build_miniapp_event_url(
        miniapp_base_url=settings.miniapp_base_url,
        public_token=token,
    )
    telegram_miniapp_url = build_telegram_miniapp_direct_link(
        bot_username=bot_username,
        miniapp_short_name=settings.telegram_miniapp_short_name,
        public_token=token,
    )

    if miniapp_url and use_web_app:
        builder.button(text="Open Event", web_app=WebAppInfo(url=miniapp_url))
    elif telegram_miniapp_url and open_event_only:
        builder.button(text="Open Event", url=telegram_miniapp_url)
    elif miniapp_url:
        builder.button(text="Open Event", url=miniapp_url)
    elif not open_event_only:
        builder.button(text="Notify me before the event", callback_data=f"er_{token}")
        builder.button(text="Back to Events", callback_data="events_back")
        builder.button(text="Share Event", callback_data=f"es_{token}")

    if event.registration_url and not open_event_only:
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
        return f"<i>{date_text} {time_text}</i> - {title_html}, {location}"

    return f"<i>{time_text}</i> - {title_html}, {location}"


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
