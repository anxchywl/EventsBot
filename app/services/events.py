from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from aiogram import Bot

from app.models.event import Event, EventCategory
from app.models.moderation import ModerationLog
from app.models.user import User
from app.models.enums import EventStatus, ModerationAction


async def get_active_categories(session: AsyncSession) -> Sequence[EventCategory]:
    result = await session.execute(
        select(EventCategory)
        .where(EventCategory.is_active.is_(True))
        .order_by(EventCategory.sort_order, EventCategory.name)
    )
    return result.scalars().all()


async def get_category_by_id(
    session: AsyncSession, category_id: int
) -> EventCategory | None:
    result = await session.execute(
        select(EventCategory).where(EventCategory.id == category_id)
    )
    return result.scalar_one_or_none()


async def create_pending_event(
    session: AsyncSession,
    creator: User,
    event_data: dict,
) -> Event:
    event = Event(
        creator_user_id=creator.id,
        title=event_data["title"],
        description=event_data["description"],
        event_date=event_data["event_date"],
        event_time=event_data["event_time"],
        location=event_data["location"],
        category_id=event_data["category_id"],
        organizer_name=event_data["organizer"],
        poster_file_id=event_data.get("poster_file_id"),
        registration_url=event_data.get("registration_url"),
        status=EventStatus.PENDING.value,
    )
    session.add(event)

    # add initial moderation log
    log = ModerationLog(
        event=event,
        action=ModerationAction.SUBMITTED.value,
    )
    session.add(log)

    await session.flush()
    return event


async def get_event_by_id(session: AsyncSession, event_id: int) -> Event | None:
    result = await session.execute(
        select(Event)
        .where(Event.id == event_id)
        .options(selectinload(Event.category), selectinload(Event.creator))
    )
    return result.scalar_one_or_none()


async def get_pending_events(session: AsyncSession) -> Sequence[Event]:
    result = await session.execute(
        select(Event)
        .where(Event.status == EventStatus.PENDING.value)
        .order_by(Event.created_at)
        .options(selectinload(Event.category), selectinload(Event.creator))
    )
    return result.scalars().all()


async def get_user_events(session: AsyncSession, user_id: int) -> Sequence[Event]:
    """Fetch all events created by a specific user."""
    result = await session.execute(
        select(Event)
        .where(Event.creator_user_id == user_id)
        .order_by(Event.event_date.desc(), Event.event_time.desc())
        .options(selectinload(Event.category))
    )
    return result.scalars().all()


async def delete_event_completely(
    session: AsyncSession, bot: Bot, event_id: int
) -> bool:
    """Instantly delete an event and clean up all related data and Telegram messages."""
    from app.services.dashboard import create_or_update_dashboard_message
    from app.models.chat import Chat

    event = await session.get(
        Event, event_id, options=[selectinload(Event.detail_messages)]
    )
    if not event:
        return False

    # 1. delete all detailed messages from telegram
    for detail in event.detail_messages:
        try:
            # fetch the chat object to get telegram_chat_id
            chat = await session.get(Chat, detail.chat_id)
            if chat:
                await bot.delete_message(chat.telegram_chat_id, detail.message_id)
        except Exception:
            pass  # message might be too old to delete or already gone

    # 2. find all chats that had this event in their dashboard
    # (these are the chats where detail_messages existed)
    chat_ids = [detail.chat_id for detail in event.detail_messages]

    # 3. delete the event from db (cascades to detail_messages, reminders, favorites, etc.)
    await session.delete(event)
    await session.flush()

    # 4. update dashboards in all affected chats
    for chat_id in chat_ids:
        chat = await session.get(Chat, chat_id)
        if chat:
            await create_or_update_dashboard_message(session, bot, chat)

    return True


async def update_event_status(
    session: AsyncSession,
    event_id: int,
    status: EventStatus,
    moderator: User,
    comment: str | None = None,
) -> Event | None:
    event = await get_event_by_id(session, event_id)
    if not event:
        return None

    event.status = status.value
    if status == EventStatus.APPROVED:
        from datetime import datetime, timezone

        event.approved_by_user_id = moderator.id
        event.approved_at = datetime.now(timezone.utc)

    event.moderation_note = comment

    # map eventstatus to moderationaction
    action_map = {
        EventStatus.APPROVED: ModerationAction.APPROVED,
        EventStatus.REJECTED: ModerationAction.REJECTED,
        EventStatus.NEEDS_CHANGES: ModerationAction.NEEDS_CHANGES,
        EventStatus.CANCELLED: ModerationAction.CANCELLED,
    }

    log = ModerationLog(
        event_id=event.id,
        moderator_user_id=moderator.id,
        action=action_map.get(status, ModerationAction.EDITED).value,
        comment=comment,
    )
    session.add(log)

    await session.flush()
    return event
