from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, func, select, String, Interval, TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.session import get_session
from app.models.enums import EventStatus
from app.models.event import Event, EventCategory
from app.models.analytics import EventAnalytics
from app.models.favorite import Favorite
from app.models.reminder import Reminder
from app.models.user import User
from app.services.analytics import record_event_action_by_ids
from app.services.events import (
    ensure_event_public_token,
    get_event_by_public_token,
)
from app.services.event_sync import latest_completed_sync_version
from app.services.telegram_links import build_telegram_miniapp_direct_link
from app.web.auth import MiniAppUser, optional_miniapp_user, require_miniapp_user, upsert_miniapp_user
from app.web.cache import TTLCache
from app.web.schemas import EventDetail, EventFilterOption, EventFiltersResponse, EventListItem, RegisterResponse
from app.web.serializers import event_detail as serialize_event_detail
from app.web.serializers import event_list_items
from app.web.telegram import get_bot_username


router = APIRouter(prefix="/api/events", tags=["miniapp-events"])
event_cache = TTLCache(ttl_seconds=20)

ALLOWED_SORTS = {
    "time_asc",
    "time_desc",
    "reminders_desc",
    "reminders_asc",
    "participants_desc",
    "participants_asc",
}
ALLOWED_RELEVANCE = {"active", "all", "archived"}


@router.get("", response_model=list[EventListItem])
async def list_events(
    sort: str = Query("time_asc"),
    relevance: str = Query("active"),
    categories: str = Query(""),
    organizers: str = Query(""),
    locations: str = Query(""),
    favorite_only: bool = Query(False),
    miniapp_user: MiniAppUser | None = Depends(optional_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventListItem]:
    user = await _optional_user(session, miniapp_user)
    sort = sort if sort in ALLOWED_SORTS else "time_asc"
    relevance = relevance if relevance in ALLOWED_RELEVANCE else "active"
    category_values = _split_filter_values(categories)
    organizer_values = _split_filter_values(organizers)
    location_values = _split_filter_values(locations)
    cache_key = (
        f"events:list:{user.id if user else 'public'}:"
        f"{sort}:{relevance}:"
        f"{','.join(category_values)}:{','.join(organizer_values)}:{','.join(location_values)}:"
        f"{int(favorite_only)}"
    )
    cached = event_cache.get(cache_key)
    if cached is not None:
        return cached

    events = await _filtered_events(
        session,
        sort=sort,
        relevance=relevance,
        categories=category_values,
        organizers=organizer_values,
        locations=location_values,
        favorite_only=favorite_only,
        user=user,
    )
    data = await event_list_items(session, events, user=user)
    event_cache.set(cache_key, data)
    return data


@router.get("/filters", response_model=EventFiltersResponse)
async def event_filters(
    session: AsyncSession = Depends(get_session),
) -> EventFiltersResponse:
    today = _today()
    category_result = await session.execute(
        select(EventCategory.slug, EventCategory.name)
        .join(Event, Event.category_id == EventCategory.id)
        .where(
            Event.status == EventStatus.APPROVED.value,
            EventCategory.is_active.is_(True),
        )
        .group_by(EventCategory.slug, EventCategory.name, EventCategory.sort_order)
        .order_by(EventCategory.sort_order, EventCategory.name)
    )
    organizer_result = await session.execute(
        select(Event.organizer_name)
        .where(
            Event.status == EventStatus.APPROVED.value,
            Event.event_date >= today,
        )
        .group_by(Event.organizer_name)
        .order_by(func.lower(Event.organizer_name))
        .limit(250)
    )
    location_result = await session.execute(
        select(Event.location)
        .where(
            Event.status == EventStatus.APPROVED.value,
        )
        .group_by(Event.location)
        .order_by(func.lower(Event.location))
        .limit(250)
    )
    return EventFiltersResponse(
        categories=[
            EventFilterOption(value=slug, label=name)
            for slug, name in category_result.all()
        ],
        organizers=[
            EventFilterOption(value=name, label=name)
            for name in organizer_result.scalars().all()
            if name
        ],
        locations=[
            EventFilterOption(value=name, label=name)
            for name in location_result.scalars().all()
            if name
        ],
    )


@router.get("/sync-version")
async def event_sync_version(
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await latest_completed_sync_version(session)


@router.get("/{public_token}", response_model=EventDetail)
async def event_detail(
    public_token: str,
    miniapp_user: MiniAppUser | None = Depends(optional_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> EventDetail:
    user = await _optional_user(session, miniapp_user)
    event = await get_event_by_public_token(session, public_token)
    if not event or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")
    ensure_event_public_token(event)
    await session.flush()

    source = "share" if public_token.startswith("event_") else "miniapp"
    await record_event_action_by_ids(
        session,
        event_id=event.id,
        user_id=user.id if user else None,
        action="open_from_share" if source == "share" else "open",
        source=source,
    )

    data = await serialize_event_detail(
        session,
        event,
        user=user,
        share_url=await _event_share_target(event.public_token),
        related_events=await _related_events(session, event),
    )
    await session.commit()
    return data


@router.post("/{public_token}/register", response_model=RegisterResponse)
async def register_event_click(
    public_token: str,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    event = await get_event_by_public_token(session, public_token)
    if not event or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    already_registered = await session.scalar(
        select(
            exists().where(
                EventAnalytics.event_id == event.id,
                EventAnalytics.user_id == user.id,
                EventAnalytics.action == "register_click",
            )
        )
    )
    if not already_registered:
        await record_event_action_by_ids(
            session,
            event_id=event.id,
            user_id=user.id,
            action="register_click",
            source="miniapp",
        )
        event_cache.clear()

    count = await session.scalar(
        select(func.count(func.distinct(EventAnalytics.user_id))).where(
            EventAnalytics.event_id == event.id,
            EventAnalytics.action == "register_click",
            EventAnalytics.user_id.is_not(None),
        )
    )
    await session.commit()
    return RegisterResponse(attendee_count=int(count or 0))


async def _related_events(session: AsyncSession, event: Event) -> list[Event]:
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.app_timezone)).date()
    result = await session.execute(
        select(Event)
        .where(
            Event.status == EventStatus.APPROVED.value,
            Event.category_id == event.category_id,
            Event.id != event.id,
            Event.event_date >= today,
        )
        .order_by(Event.event_date, Event.event_time)
        .options(selectinload(Event.category))
        .limit(3)
    )
    return list(result.scalars().all())


async def _optional_user(
    session: AsyncSession,
    miniapp_user: MiniAppUser | None,
) -> User | None:
    if not miniapp_user:
        return None
    return await upsert_miniapp_user(session, miniapp_user)


async def _filtered_events(
    session: AsyncSession,
    *,
    sort: str,
    relevance: str,
    categories: list[str],
    organizers: list[str],
    locations: list[str],
    favorite_only: bool,
    user: User | None,
) -> list[Event]:
    today = _today()
    reminder_counts = (
        select(Reminder.event_id, func.count(Reminder.id).label("reminder_total"))
        .group_by(Reminder.event_id)
        .subquery()
    )
    favorite_counts = (
        select(Favorite.event_id, func.count(Favorite.id).label("favorite_total"))
        .group_by(Favorite.event_id)
        .subquery()
    )
    participant_total = (
        func.coalesce(reminder_counts.c.reminder_total, 0)
        + func.coalesce(favorite_counts.c.favorite_total, 0)
    )

    stmt = (
        select(Event)
        .join(Event.category)
        .outerjoin(reminder_counts, reminder_counts.c.event_id == Event.id)
        .outerjoin(favorite_counts, favorite_counts.c.event_id == Event.id)
        .where(Event.status == EventStatus.APPROVED.value)
        .options(selectinload(Event.category))
        .limit(200)
    )

    event_start_utc = func.timezone(
        "UTC", 
        func.timezone(
            Event.timezone, 
            func.cast(func.cast(Event.event_date, String) + ' ' + func.cast(Event.event_time, String), TIMESTAMP)
        )
    )
    
    if favorite_only:
        if user is None:
            return []
        stmt = stmt.where(
            exists().where(
                Favorite.event_id == Event.id,
                Favorite.user_id == user.id,
            )
        )

    if relevance == "active":
        stmt = stmt.where(event_start_utc + timedelta(hours=2) >= func.timezone("UTC", func.now()))
    elif relevance == "archived":
        stmt = stmt.where(event_start_utc + timedelta(hours=2) < func.timezone("UTC", func.now()))

    if categories:
        stmt = stmt.where(EventCategory.slug.in_(categories))
    if organizers:
        stmt = stmt.where(Event.organizer_name.in_(organizers))
    if locations:
        stmt = stmt.where(Event.location.in_(locations))

    if sort == "time_desc":
        stmt = stmt.order_by(Event.event_date.desc(), Event.event_time.desc(), Event.id.desc())
    elif sort == "reminders_desc":
        stmt = stmt.order_by(func.coalesce(reminder_counts.c.reminder_total, 0).desc(), Event.event_date, Event.event_time)
    elif sort == "reminders_asc":
        stmt = stmt.order_by(func.coalesce(reminder_counts.c.reminder_total, 0), Event.event_date, Event.event_time)
    elif sort == "participants_desc":
        stmt = stmt.order_by(participant_total.desc(), Event.event_date, Event.event_time)
    elif sort == "participants_asc":
        stmt = stmt.order_by(participant_total, Event.event_date, Event.event_time)
    else:
        stmt = stmt.order_by(Event.event_date, Event.event_time, Event.id)

    result = await session.execute(stmt)
    return list(result.scalars().all())


def _split_filter_values(value: str) -> list[str]:
    return sorted({item.strip() for item in value.split(",") if item.strip()})


def _today():
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


async def _event_share_target(public_token: str) -> str:
    settings = get_settings()
    return build_telegram_miniapp_direct_link(
        bot_username=await get_bot_username(),
        miniapp_short_name=settings.telegram_miniapp_short_name,
        public_token=public_token,
    ) or f"/events/{public_token}"
