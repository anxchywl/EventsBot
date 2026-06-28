from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models.enums import EventStatus
from app.services.analytics import record_event_action_by_ids
from app.services.events import get_event_by_public_token
from app.services.favorites import add_favorite, get_user_favorite_events, remove_favorite
from app.services.friends import friend_ids, public_user_summary
from app.web.auth import MiniAppUser, require_current_miniapp_user, upsert_miniapp_user
from app.web.limiter import check_rate_limit
from app.web.realtime import publish_miniapp_event
from app.web.routers.events import event_cache, validate_public_token
from app.web.schemas import EventListItem, FavoriteResponse
from app.web.serializers import event_list_items


router = APIRouter(tags=["miniapp-favorites"])

# list saved events for the current user
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


# save one event and refresh related counts
@router.post("/api/events/{public_token}/favorite", response_model=FavoriteResponse)
async def favorite_event(
    public_token: str,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    await check_rate_limit(f"rate:user:{user.id}:fav", 30, 60, "Too many favorite attempts. Try again later.")
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


# remove one saved event and refresh related counts
@router.delete("/api/events/{public_token}/favorite", response_model=FavoriteResponse)
async def unfavorite_event(
    public_token: str,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    await check_rate_limit(f"rate:user:{user.id}:fav", 30, 60, "Too many favorite attempts. Try again later.")
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
