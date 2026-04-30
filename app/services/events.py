from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


async def get_category_by_id(session: AsyncSession, category_id: int) -> EventCategory | None:
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
    
    # Add initial moderation log
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
    
    # Map EventStatus to ModerationAction
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
        comment=comment
    )
    session.add(log)
    
    await session.flush()
    return event
