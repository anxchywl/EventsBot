import logging
from typing import Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from aiogram import Bot

from app.models.event import Event, EventCategory
from app.models.moderation import ModerationLog
from app.models.user import User
from app.models.enums import EventStatus, ModerationAction

logger = logging.getLogger(__name__)


# loads active event categories
async def get_active_categories(session: AsyncSession) -> Sequence[EventCategory]:
    result = await session.execute(
        select(EventCategory)
        .where(EventCategory.is_active.is_(True))
        .order_by(EventCategory.sort_order, EventCategory.name)
    )
    return result.scalars().all()


# finds a category by id
async def get_category_by_id(
    session: AsyncSession, category_id: int
) -> EventCategory | None:
    result = await session.execute(
        select(EventCategory).where(EventCategory.id == category_id)
    )
    return result.scalar_one_or_none()


# creates a pending event and its moderation log
async def create_pending_event(
    session: AsyncSession,
    creator: User,
    event_data: dict,
) -> Event:
    # build the event from collected form data
    event = Event(
        creator_user_id=creator.id,
        public_token=str(uuid4()),
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


# loads one event with category and creator
async def get_event_by_id(session: AsyncSession, event_id: int) -> Event | None:
    result = await session.execute(
        select(Event)
        .where(Event.id == event_id)
        .options(selectinload(Event.category), selectinload(Event.creator))
    )
    return result.scalar_one_or_none()


async def get_event_by_public_token(
    session: AsyncSession, public_token: str
) -> Event | None:
    public_token = normalize_public_token(public_token)
    result = await session.execute(
        select(Event)
        .where(Event.public_token == public_token)
        .options(selectinload(Event.category), selectinload(Event.creator))
    )
    return result.scalar_one_or_none()


async def get_available_event_by_public_token(
    session: AsyncSession, public_token: str
) -> Event | None:
    public_token = normalize_public_token(public_token)
    result = await session.execute(
        select(Event)
        .where(
            Event.public_token == public_token,
            Event.status == EventStatus.APPROVED.value,
        )
        .options(selectinload(Event.category), selectinload(Event.creator))
    )
    return result.scalar_one_or_none()


async def get_approved_upcoming_events(session: AsyncSession) -> Sequence[Event]:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.config import get_settings

    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.app_timezone)).date()

    result = await session.execute(
        select(Event)
        .where(
            Event.status == EventStatus.APPROVED.value,
            Event.event_date >= today,
        )
        .order_by(Event.event_date, Event.event_time)
        .options(selectinload(Event.category))
    )
    return result.scalars().all()


def ensure_event_public_token(event: Event) -> str:
    if not event.public_token:
        event.public_token = str(uuid4())
    return event.public_token


def normalize_public_token(public_token: str) -> str:
    token = public_token.strip()
    if token.startswith("event_"):
        token = token.removeprefix("event_")
    return token


# loads events waiting for moderation
async def get_pending_events(session: AsyncSession) -> Sequence[Event]:
    result = await session.execute(
        select(Event)
        .where(Event.status == EventStatus.PENDING.value)
        .order_by(Event.created_at, Event.id)
        .options(selectinload(Event.category), selectinload(Event.creator))
    )
    pending = result.scalars().all()

    latest_by_source: dict[int, Event] = {}
    for event in pending:
        source_id = event.parent_event_id or event.id
        current = latest_by_source.get(source_id)
        if current is None or (event.created_at, event.id) > (
            current.created_at,
            current.id,
        ):
            latest_by_source[source_id] = event

    return sorted(
        latest_by_source.values(),
        key=lambda event: (event.created_at, event.id),
    )


# loads events created by a user
async def get_user_events(session: AsyncSession, user_id: int) -> Sequence[Event]:
    """fetch all events created by a specific user."""
    result = await session.execute(
        select(Event)
        .where(Event.creator_user_id == user_id)
        .order_by(Event.event_date.desc(), Event.event_time.desc())
        .options(selectinload(Event.category))
    )
    return result.scalars().all()


# deletes an event and related telegram messages, then signals dashboard refresh
async def delete_event_completely(
    session: AsyncSession, bot: Bot, event_id: int
) -> bool:
    """instantly delete an event and clean up all related data and telegram messages."""
    # load event with detail messages and their associated chats preloaded
    from sqlalchemy.orm import selectinload
    from app.models.event import EventDetailMessage

    event = await session.get(
        Event,
        event_id,
        options=[
            selectinload(Event.detail_messages).selectinload(EventDetailMessage.chat)
        ],
    )
    if not event:
        return False

    # collect chat ids for dashboard refresh
    chat_ids = set()
    for detail in event.detail_messages:
        chat_ids.add(detail.chat_id)
        if detail.chat:
            try:
                await bot.delete_message(
                    chat_id=detail.chat.telegram_chat_id,
                    message_id=detail.message_id,
                )
            except Exception as e:
                logger.warning(
                    f"failed to delete message {detail.message_id} in chat {detail.chat.id}: {e}"
                )

    await session.delete(event)
    await session.flush()

    # signal dashboard bus for a debounced refresh (non-blocking)
    if chat_ids:
        try:
            from app.services.dashboard_bus import get_bus

            get_bus().schedule_refresh(chat_ids)
        except Exception:
            pass

    return True


# updates an event status and records moderation
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

    # set approval metadata when needed
    event.status = status.value
    if status == EventStatus.APPROVED:
        from datetime import datetime, timezone

        event.approved_by_user_id = moderator.id
        event.approved_at = datetime.now(timezone.utc)

    event.moderation_note = comment

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
    # re-fetch with all relationships needed by publisher loaded
    return await get_event_by_id(session, event.id)


# removes the parent pending event and all its draft siblings when a new draft is submitted
async def cleanup_previous_drafts(
    session: AsyncSession, parent_event_id: int, new_draft_id: int
) -> None:
    """
    used when the *original* event is still pending (never approved).
    1. detaches the new draft from its parent (makes it stand-alone)
    2. deletes the original pending event and all its other draft children
    so only the latest draft remains as the main event.
    """
    # detach the new draft from the parent so it becomes independent
    new_draft = await session.get(Event, new_draft_id)
    if new_draft:
        new_draft.parent_event_id = None

    # delete the parent event (cascade will delete any other drafts)
    parent = await session.get(Event, parent_event_id)
    if parent:
        session.delete(parent)

    await session.flush()


# deletes every other pending draft that shares the same parent as the new draft
async def replace_pending_drafts_for_parent(
    session: AsyncSession, parent_event_id: int, new_draft_id: int
) -> None:
    """
    ensures only one pending draft exists per parent event at any time.

    called whenever a user re-submits an update while a previous draft is
    still awaiting moderation.  all stale pending drafts (same parent_event_id,
    status == 'pending') are deleted, except the newly-created one.
    """
    from sqlalchemy import and_

    result = await session.execute(
        select(Event).where(
            and_(
                Event.parent_event_id == parent_event_id,
                Event.status == EventStatus.PENDING.value,
                Event.id != new_draft_id,
            )
        )
    )
    stale_drafts = result.scalars().all()
    for draft in stale_drafts:
        await session.delete(draft)

    if stale_drafts:
        await session.flush()
        logger.info(
            "deleted %d stale pending draft(s) for parent event %d (kept draft %d)",
            len(stale_drafts),
            parent_event_id,
            new_draft_id,
        )
