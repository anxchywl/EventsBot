from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.services.analytics import record_event_action_by_ids
from app.services.events import get_available_event_by_public_token
from app.services.telegram_links import (
    build_telegram_miniapp_direct_link,
    build_telegram_share_link,
)
from app.web.auth import MiniAppUser, require_miniapp_user, upsert_miniapp_user
from app.web.schemas import ActionResponse
from app.web.telegram import get_bot_username


router = APIRouter(tags=["miniapp-sharing"])


@router.post("/api/events/{public_token}/share", response_model=ActionResponse)
async def share_event(
    public_token: str,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    target = build_telegram_miniapp_direct_link(
        bot_username=await get_bot_username(),
        miniapp_short_name=get_settings().telegram_miniapp_short_name,
        public_token=event.public_token,
    ) or f"/events/{event.public_token}"
    await record_event_action_by_ids(
        session,
        event_id=event.id,
        user_id=user.id,
        action="share_click",
        source="miniapp",
    )
    await session.commit()
    return ActionResponse(
        message="Share this event.",
        url=build_telegram_share_link(url=target, text=event.title),
    )
