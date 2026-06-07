from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
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
from app.services.telegram_links import build_telegram_miniapp_direct_link, build_telegram_text_share_link
from app.web.auth import MiniAppUser, optional_current_miniapp_user, require_current_miniapp_user, upsert_miniapp_user, verify_session_token
from app.web.cache import TTLCache
from app.web.schemas import EventDetail, EventFilterOption, EventFiltersResponse, EventListItem, RegisterResponse
from app.web.serializers import event_detail as serialize_event_detail
from app.web.serializers import event_list_items
from app.web.telegram import get_bot_username
from app.web.realtime import subscribe_miniapp_events


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
MAX_FILTER_VALUES = 25
FILTER_VALUE_MAX_LEN = 100
_PUBLIC_TOKEN_RE = re.compile(r"^(event_)?[0-9a-fA-F-]{36}$")


# reject malformed event tokens before database lookup
def validate_public_token(public_token: str) -> str:
    token = public_token.strip()
    if not _PUBLIC_TOKEN_RE.fullmatch(token):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")
    return token


# list approved events with user-specific decorations
@router.get("", response_model=list[EventListItem])
async def list_events(
    sort: str = Query("time_asc", max_length=32),
    relevance: str = Query("active", max_length=32),
    categories: str = Query("", max_length=2500),
    organizers: str = Query("", max_length=2500),
    locations: str = Query("", max_length=2500),
    favorite_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=5000),
    miniapp_user: MiniAppUser | None = Depends(optional_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventListItem]:
    user = await _optional_user(session, miniapp_user)
    if sort not in ALLOWED_SORTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid sort")
    if relevance not in ALLOWED_RELEVANCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid relevance")
    category_values = _split_filter_values(categories)
    organizer_values = _split_filter_values(organizers)
    location_values = _split_filter_values(locations)
    cache_key = (
        f"events:list:{user.id if user else 'public'}:"
        f"{sort}:{relevance}:{limit}:{offset}:"
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
        limit=limit,
        offset=offset,
    )
    data = await event_list_items(session, events, user=user)
    event_cache.set(cache_key, data)
    return data


# expose filter options for the mini app
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


# report the latest completed event sync version
@router.get("/sync-version")
async def event_sync_version(
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await latest_completed_sync_version(session)


# stream review deletion updates to connected clients
@router.get("/review-updates")
async def review_updates() -> StreamingResponse:
    async def stream():
        yield ": connected\n\n"
        iterator = subscribe_miniapp_events()
        while True:
            try:
                # wait for next event or timeout for keep-alive ping
                message = await asyncio.wait_for(anext(iterator), timeout=15.0)
                yield f"event: {message['type']}\n"
                yield f"data: {json.dumps(message)}\n\n"
            except asyncio.TimeoutError:
                # send a comment ping to keep connection alive and detect drops
                yield ": ping\n\n"
            except StopAsyncIteration:
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# stream mini app updates with keepalive pings
@router.get("/updates")
async def miniapp_updates(
    token: str = Query(..., min_length=1, max_length=4096),
) -> StreamingResponse:
    from app.db.session import async_session_maker
    miniapp_user = verify_session_token(token)
    async with async_session_maker() as session:
        user = await upsert_miniapp_user(session, miniapp_user)
        await session.commit()
        user_id = user.id

    async def stream():
        yield ": connected\n\n"
        iterator = subscribe_miniapp_events(user_id)
        while True:
            try:
                message = await asyncio.wait_for(anext(iterator), timeout=15.0)
                yield f"event: {message['type']}\n"
                yield f"data: {json.dumps(message)}\n\n"
            except asyncio.TimeoutError:
                yield ": ping\n\n"
            except StopAsyncIteration:
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# load one approved event by public token
@router.get("/{public_token}", response_model=EventDetail)
async def event_detail(
    public_token: str,
    miniapp_user: MiniAppUser | None = Depends(optional_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> EventDetail:
    user = await _optional_user(session, miniapp_user)
    public_token = validate_public_token(public_token)
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
        share_url=await _event_share_url(event),
        related_events=await _related_events(session, event),
    )
    await session.commit()
    return data


# record registration intent before redirecting users
@router.post("/{public_token}/register", response_model=RegisterResponse)
async def register_event_click(
    public_token: str,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    public_token = validate_public_token(public_token)
    event = await get_event_by_public_token(session, public_token)
    if not event or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    already_registered = await session.scalar(
        select(
            exists()
            .select_from(EventAnalytics)
            .join(User, EventAnalytics.user_id == User.id)
            .where(
                EventAnalytics.event_id == event.id,
                User.telegram_id == user.telegram_id,
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
        select(func.count(func.distinct(User.telegram_id)))
        .select_from(EventAnalytics)
        .join(User, EventAnalytics.user_id == User.id)
        .where(
            EventAnalytics.event_id == event.id,
            EventAnalytics.action == "register_click",
        )
    )
    await session.commit()
    return RegisterResponse(attendee_count=int(count or 0))


# recommend nearby approved events from the same category
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


# load user context when a valid session exists
async def _optional_user(
    session: AsyncSession,
    miniapp_user: MiniAppUser | None,
) -> User | None:
    if not miniapp_user:
        return None
    return await upsert_miniapp_user(session, miniapp_user)


# apply mini app filters to approved events
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
    limit: int,
    offset: int,
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
        .offset(offset)
        .limit(limit)
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


# parse comma-separated filter query values
def _split_filter_values(value: str) -> list[str]:
    items = sorted({item.strip() for item in value.split(",") if item.strip()})
    if len(items) > MAX_FILTER_VALUES or any(len(item) > FILTER_VALUE_MAX_LEN for item in items):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Too many filter values")
    return items


# anchor date filters to local day boundaries
def _today():
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


# choose the safest share target for one event
async def _event_share_target(public_token: str) -> str:
    settings = get_settings()
    return build_telegram_miniapp_direct_link(
        bot_username=await get_bot_username(),
        miniapp_short_name=settings.telegram_miniapp_short_name,
        public_token=public_token,
    ) or f"/events/{public_token}"


# build public share urls from event tokens
async def _event_share_url(event: Event) -> str:
    return build_telegram_text_share_link(
        text=event.title,
        url=await _event_share_target(event.public_token),
    )
