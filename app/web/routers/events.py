from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.session import get_session
from app.models.enums import EventStatus
from app.models.event import Event
from app.models.user import User
from app.services.analytics import record_event_action_by_ids
from app.services.events import (
    ensure_event_public_token,
    get_approved_upcoming_events,
    get_available_event_by_public_token,
)
from app.services.telegram_links import build_telegram_miniapp_direct_link
from app.web.auth import MiniAppUser, optional_miniapp_user, upsert_miniapp_user
from app.web.cache import TTLCache
from app.web.schemas import EventDetail, EventListItem
from app.web.serializers import event_detail as serialize_event_detail
from app.web.serializers import event_list_items
from app.web.telegram import get_bot_username


router = APIRouter(prefix="/api/events", tags=["miniapp-events"])
event_cache = TTLCache(ttl_seconds=20)


@router.get("", response_model=list[EventListItem])
async def list_events(
    miniapp_user: MiniAppUser | None = Depends(optional_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventListItem]:
    user = await _optional_user(session, miniapp_user)
    cache_key = f"events:list:{user.id if user else 'public'}"
    cached = event_cache.get(cache_key)
    if cached is not None:
        return cached

    events = list(await get_approved_upcoming_events(session))
    data = await event_list_items(session, events, user=user)
    event_cache.set(cache_key, data)
    return data


@router.get("/{public_token}", response_model=EventDetail)
async def event_detail(
    public_token: str,
    miniapp_user: MiniAppUser | None = Depends(optional_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> EventDetail:
    user = await _optional_user(session, miniapp_user)
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
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


async def _event_share_target(public_token: str) -> str:
    settings = get_settings()
    return build_telegram_miniapp_direct_link(
        bot_username=await get_bot_username(),
        miniapp_short_name=settings.telegram_miniapp_short_name,
        public_token=public_token,
    ) or f"/events/{public_token}"
