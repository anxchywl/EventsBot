from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models.enums import EventStatus
from app.services.analytics import record_event_action_by_ids
from app.services.events import get_event_by_public_token
from app.services.favorites import add_favorite, get_user_favorite_events, remove_favorite
from app.services.friends import friend_ids, public_user_summary
from app.web.auth import MiniAppUser, require_current_miniapp_user, upsert_miniapp_user
from app.web.realtime import publish_miniapp_event
from app.web.routers.events import event_cache, validate_public_token
from app.web.schemas import EventListItem, FavoriteResponse
from app.web.serializers import event_list_items


router = APIRouter(tags=["miniapp-favorites"])

import time

_FAVORITE_RATE_LIMITS: dict[str, list[float]] = {}

def _check_rate_limit(request: Request, user_id: int, limit: int, window_seconds: int) -> None:
    now = time.time()
    cutoff = now - window_seconds
    host = request.client.host if request.client else "unknown"
    key = f"favorite:{user_id}:{host}"
    hits = [ts for ts in _FAVORITE_RATE_LIMITS.get(key, []) if ts > cutoff]
    if len(hits) >= limit:
        _FAVORITE_RATE_LIMITS[key] = hits
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many favorite attempts. Try again later.")
    hits.append(now)
    _FAVORITE_RATE_LIMITS[key] = hits

    # Prevent memory leaks by pruning stale keys when dict grows large
    if len(_FAVORITE_RATE_LIMITS) > 10000:
        for k in list(_FAVORITE_RATE_LIMITS.keys()):
            _FAVORITE_RATE_LIMITS[k] = [ts for ts in _FAVORITE_RATE_LIMITS[k] if ts > cutoff]
            if not _FAVORITE_RATE_LIMITS[k]:
                del _FAVORITE_RATE_LIMITS[k]

@router.get("/api/favorites", response_model=list[EventListItem])
async def list_favorites(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=5000),
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventListItem]:
    user = await upsert_miniapp_user(session, miniapp_user)
    today = datetime.now(ZoneInfo(get_settings().app_timezone)).date()
    events = list(await get_user_favorite_events(session, user, limit, offset, today))
    return await event_list_items(session, events, user=user)


@router.post("/api/events/{public_token}/favorite", response_model=FavoriteResponse)
async def favorite_event(
    public_token: str,
    request: Request,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    _check_rate_limit(request, user.id, limit=30, window_seconds=60)
    public_token = validate_public_token(public_token)
    event = await get_event_by_public_token(session, public_token)
    if not event or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    changed = await add_favorite(session, user, event)
    if changed:
        await record_event_action_by_ids(
            session,
            event_id=event.id,
            user_id=user.id,
            action="favorite_add",
            source="miniapp",
        )
    await session.commit()
    if changed:
        targets = list(await friend_ids(session, user.id)) + [user.id]
        await publish_miniapp_event(
            "favorite_changed",
            {
                "event_token": event.public_token,
                "user_id": user.id,
                "is_favorite": True,
                "friend": await public_user_summary(session, user, current_user=user),
                "target_user_ids": targets,
            },
        )
    event_cache.clear()
    return FavoriteResponse(is_favorite=True)


@router.delete("/api/events/{public_token}/favorite", response_model=FavoriteResponse)
async def unfavorite_event(
    public_token: str,
    request: Request,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    _check_rate_limit(request, user.id, limit=30, window_seconds=60)
    public_token = validate_public_token(public_token)
    event = await get_event_by_public_token(session, public_token)
    if not event or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    changed = await remove_favorite(session, user, event)
    if changed:
        await record_event_action_by_ids(
            session,
            event_id=event.id,
            user_id=user.id,
            action="favorite_remove",
            source="miniapp",
        )
    await session.commit()
    if changed:
        targets = list(await friend_ids(session, user.id)) + [user.id]
        await publish_miniapp_event(
            "favorite_changed",
            {
                "event_token": event.public_token,
                "user_id": user.id,
                "is_favorite": False,
                "target_user_ids": targets,
            },
        )
    event_cache.clear()
    return FavoriteResponse(is_favorite=False)
