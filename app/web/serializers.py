from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event
from app.models.enums import EventStatus
from app.models.analytics import EventAnalytics
from app.models.user import User
from app.models.reminder import Reminder
from app.models.rating import Rating
from app.models.comment import Comment
from app.services.favorites import get_favorite_event_ids, is_event_favorite
from app.services.telegram_links import build_telegram_share_link
from app.web.schemas import EventDetail, EventListItem, ReviewDetail


PALETTE_KEYS = ("aurora", "sunset", "mint", "violet", "sky", "rose")


async def event_list_item(
    session: AsyncSession,
    event: Event,
    *,
    user: User | None = None,
    favorite_ids: set[int] | None = None,
    reminder_counts: dict[int, int] | None = None,
    attendee_counts: dict[int, int] | None = None,
) -> EventListItem:
    favorites = favorite_ids or set()
    counts = reminder_counts or {}
    attendees = attendee_counts or {}
    return EventListItem(
        token=event.public_token,
        title=event.title,
        date=event.event_date.isoformat(),
        time=event.event_time.strftime("%H:%M"),
        location=event.location,
        organizer=event.organizer_name,
        category=event.category.name,
        is_favorite=event.id in favorites
        if favorite_ids is not None
        else await is_event_favorite(session, user, event.id),
        reminder_count=counts.get(event.id, 0),
        attendee_count=attendees.get(event.id, 0),
        is_ended=is_event_ended(event),
        is_archived=is_event_archived(event),
        cover_url=event_cover_url(event),
    )


async def event_list_items(
    session: AsyncSession,
    events: list[Event],
    *,
    user: User | None = None,
) -> list[EventListItem]:
    event_ids = [event.id for event in events]
    favorite_ids = await get_favorite_event_ids(session, user, event_ids)
    reminder_counts = await get_reminder_counts(session, user, event_ids)
    attendee_counts = await get_attendee_counts(session, event_ids)
    return [
        await event_list_item(
            session,
            event,
            user=user,
            favorite_ids=favorite_ids,
            reminder_counts=reminder_counts,
            attendee_counts=attendee_counts,
        )
        for event in events
    ]


async def event_detail(
    session: AsyncSession,
    event: Event,
    *,
    user: User | None,
    share_url: str,
    related_events: list[Event],
) -> EventDetail:
    total_attendees = await attendee_count(session, event.id)
    favorite = await is_event_favorite(session, user, event.id)
    reminder_ids, reminder_offsets = await user_reminder_details(session, user, event.id)

    # Fetch ratings
    stmt_ratings = select(Rating).where(Rating.event_id == event.id).options(selectinload(Rating.user))
    ratings = (await session.execute(stmt_ratings)).scalars().all()
    verified_ratings = [r for r in ratings if r.user.is_verified]
    rating_count = len(verified_ratings)
    average_rating = sum(r.score for r in verified_ratings) / rating_count if rating_count > 0 else None

    # Fetch comments
    stmt_comments = select(Comment).where(Comment.event_id == event.id).options(selectinload(Comment.user))
    comments = (await session.execute(stmt_comments)).scalars().all()
    verified_comments = [c for c in comments if c.user.is_verified]

    # Merge ratings and comments by user_id
    user_map = {}
    for r in verified_ratings:
        user_map[r.user_id] = {
            "comment_id": None,
            "rating_id": r.id,
            "nickname": r.user.nickname or "Anonymous",
            "content": None,
            "score": r.score,
            "created_at": r.created_at.isoformat(),
            "is_own": user is not None and r.user_id == user.id
        }
    for c in verified_comments:
        if c.user_id in user_map:
            user_map[c.user_id]["comment_id"] = c.id
            user_map[c.user_id]["content"] = c.content
        else:
            user_map[c.user_id] = {
                "comment_id": c.id,
                "rating_id": None,
                "nickname": c.user.nickname or "Anonymous",
                "content": c.content,
                "score": None,
                "created_at": c.created_at.isoformat(),
                "is_own": user is not None and c.user_id == user.id
            }

    reviews_list = list(user_map.values())
    reviews_list.sort(key=lambda x: (not x["is_own"], x["created_at"]), reverse=True)
    reviews = [ReviewDetail(**val) for val in reviews_list]

    return EventDetail(
        token=event.public_token,
        title=event.title,
        description=event.description,
        date=event.event_date.isoformat(),
        time=event.event_time.strftime("%H:%M"),
        location=event.location,
        map_url=f"https://maps.google.com/?q={quote_plus(event.location)}",
        organizer=event.organizer_name,
        category=event.category.name,
        registration_url=event.registration_url,
        cover_url=event_cover_url(event),
        attendee_count=total_attendees,
        share_url=build_telegram_share_link(url=share_url, text=event.title),
        is_favorite=favorite,
        reminder_offsets=reminder_offsets,
        reminder_ids=reminder_ids,
        background_seed=event.public_token,
        palette_key=palette_key(event.public_token),
        is_archived=is_event_archived(event),
        related_events=await event_list_items(session, related_events, user=user),
        average_rating=average_rating,
        rating_count=rating_count,
        reviews=reviews,
    )


async def attendee_count(session: AsyncSession, event_id: int) -> int:
    registered = await session.scalar(
        select(func.count(func.distinct(EventAnalytics.user_id))).where(
            EventAnalytics.event_id == event_id,
            EventAnalytics.action == "register_click",
            EventAnalytics.user_id.is_not(None),
        )
    )
    return int(registered or 0)


async def get_attendee_counts(
    session: AsyncSession,
    event_ids: list[int],
) -> dict[int, int]:
    if not event_ids:
        return {}
    registered_result = await session.execute(
        select(EventAnalytics.event_id, func.count(func.distinct(EventAnalytics.user_id)))
        .where(
            EventAnalytics.event_id.in_(event_ids),
            EventAnalytics.action == "register_click",
            EventAnalytics.user_id.is_not(None),
        )
        .group_by(EventAnalytics.event_id)
    )
    counts = {event_id: 0 for event_id in event_ids}
    for event_id, count in registered_result.all():
        counts[event_id] = int(count)
    return counts


async def get_reminder_counts(
    session: AsyncSession,
    user: User | None,
    event_ids: list[int],
) -> dict[int, int]:
    if not event_ids:
        return {}
    result = await session.execute(
        select(Reminder.event_id, func.count(Reminder.id))
        .where(
            Reminder.event_id.in_(event_ids),
            Reminder.status == "scheduled",
        )
        .group_by(Reminder.event_id)
    )
    return {event_id: int(count) for event_id, count in result.all()}


async def user_reminder_offsets(
    session: AsyncSession,
    user: User | None,
    event_id: int,
) -> list[int]:
    if not user:
        return []
    result = await session.execute(
        select(Reminder.offset_minutes)
        .where(
            Reminder.user_id == user.id,
            Reminder.event_id == event_id,
            Reminder.status == "scheduled",
        )
        .order_by(Reminder.offset_minutes)
    )
    return list(result.scalars().all())


async def user_reminder_details(
    session: AsyncSession,
    user: User | None,
    event_id: int,
) -> tuple[list[int], list[int]]:
    if not user:
        return [], []
    result = await session.execute(
        select(Reminder.id, Reminder.offset_minutes)
        .where(
            Reminder.user_id == user.id,
            Reminder.event_id == event_id,
            Reminder.status == "scheduled",
        )
        .order_by(Reminder.offset_minutes)
    )
    rows = result.all()
    return [row[0] for row in rows], [row[1] for row in rows]


def event_cover_url(event: Event) -> str | None:
    return f"/api/events/{event.public_token}/cover" if event.poster_file_id else None


def is_event_ended(event: Event) -> bool:
    try:
        tz = ZoneInfo(event.timezone)
    except Exception:
        tz = UTC
    event_dt = datetime.combine(event.event_date, event.event_time).replace(tzinfo=tz)
    return event_dt + timedelta(hours=2) < datetime.now(tz)


def is_event_archived(event: Event) -> bool:
    return event.status == EventStatus.ARCHIVED.value


def palette_key(token: str) -> str:
    total = sum(ord(char) for char in token)
    return PALETTE_KEYS[total % len(PALETTE_KEYS)]
