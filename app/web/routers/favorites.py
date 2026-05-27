from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.services.analytics import record_event_action_by_ids
from app.services.events import get_event_by_public_token
from app.services.favorites import add_favorite, get_user_favorite_events, remove_favorite
from app.web.auth import MiniAppUser, require_miniapp_user, upsert_miniapp_user
from app.web.routers.events import event_cache
from app.web.schemas import EventListItem, FavoriteResponse
from app.web.serializers import event_list_items


router = APIRouter(tags=["miniapp-favorites"])


@router.get("/api/favorites", response_model=list[EventListItem])
async def list_favorites(
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventListItem]:
    user = await upsert_miniapp_user(session, miniapp_user)
    events = list(await get_user_favorite_events(session, user))
    today = datetime.now(ZoneInfo(get_settings().app_timezone)).date()
    events.sort(key=lambda event: (event.event_date < today, event.event_date, event.event_time))
    return await event_list_items(session, events, user=user)


@router.post("/api/events/{public_token}/favorite", response_model=FavoriteResponse)
async def favorite_event(
    public_token: str,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    event = await get_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    if await add_favorite(session, user, event):
        await record_event_action_by_ids(
            session,
            event_id=event.id,
            user_id=user.id,
            action="favorite_add",
            source="miniapp",
        )
    await session.commit()
    event_cache.clear()
    return FavoriteResponse(is_favorite=True)


@router.delete("/api/events/{public_token}/favorite", response_model=FavoriteResponse)
async def unfavorite_event(
    public_token: str,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    event = await get_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    if await remove_favorite(session, user, event):
        await record_event_action_by_ids(
            session,
            event_id=event.id,
            user_id=user.id,
            action="favorite_remove",
            source="miniapp",
        )
    await session.commit()
    event_cache.clear()
    return FavoriteResponse(is_favorite=False)
