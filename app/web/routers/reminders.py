from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.reminder import Reminder
from app.services.events import get_available_event_by_public_token
from app.services.reminders import (
    cancel_reminder,
    get_user_scheduled_reminders,
    schedule_reminder_offset,
)
from app.web.auth import MiniAppUser, require_current_miniapp_user, upsert_miniapp_user
from app.web.routers.events import event_cache, validate_public_token
from app.web.schemas import ActionResponse, ReminderGroup, ReminderItem, ReminderRequest
from app.web.serializers import event_list_item


router = APIRouter(tags=["miniapp-reminders"])

import time

_REMINDER_RATE_LIMITS: dict[str, list[float]] = {}

def _check_rate_limit(request: Request, user_id: int, limit: int, window_seconds: int) -> None:
    now = time.time()
    cutoff = now - window_seconds
    host = request.client.host if request.client else "unknown"
    key = f"reminder:{user_id}:{host}"
    hits = [ts for ts in _REMINDER_RATE_LIMITS.get(key, []) if ts > cutoff]
    if len(hits) >= limit:
        _REMINDER_RATE_LIMITS[key] = hits
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many reminder attempts. Try again later.")
    hits.append(now)
    _REMINDER_RATE_LIMITS[key] = hits

    # Prevent memory leaks by pruning stale keys when dict grows large
    if len(_REMINDER_RATE_LIMITS) > 10000:
        for k in list(_REMINDER_RATE_LIMITS.keys()):
            _REMINDER_RATE_LIMITS[k] = [ts for ts in _REMINDER_RATE_LIMITS[k] if ts > cutoff]
            if not _REMINDER_RATE_LIMITS[k]:
                del _REMINDER_RATE_LIMITS[k]


@router.get("/api/reminders", response_model=list[ReminderGroup])
async def list_reminders(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=5000),
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[ReminderGroup]:
    user = await upsert_miniapp_user(session, miniapp_user)
    reminders = await get_user_scheduled_reminders(session, user, limit, offset)
    groups: dict[str, list[ReminderItem]] = defaultdict(list)
    for reminder in reminders:
        key = reminder.remind_at.date().isoformat()
        groups[key].append(await _reminder_item(session, reminder, user))
    return [
        ReminderGroup(date=date, reminders=items)
        for date, items in sorted(groups.items(), key=lambda item: item[0])
    ]


@router.post("/api/events/{public_token}/reminders", response_model=ActionResponse)
async def create_reminder(
    public_token: str,
    payload: ReminderRequest,
    request: Request,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    _check_rate_limit(request, user.id, limit=20, window_seconds=3600)
    public_token = validate_public_token(public_token)
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    try:
        await schedule_reminder_offset(session, user, event, payload.offset_minutes)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await session.commit()
    event_cache.clear()
    return ActionResponse(message="Reminder set.")


@router.delete("/api/reminders/{reminder_id}", response_model=ActionResponse)
async def delete_reminder(
    reminder_id: int,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    event_id = await cancel_reminder(session, user, reminder_id)
    if event_id is None:
        await session.commit()
        event_cache.clear()
        return ActionResponse(message="Reminder removed.")
    await session.commit()
    event_cache.clear()
    return ActionResponse(message="Reminder removed.")


async def _reminder_item(
    session: AsyncSession,
    reminder: Reminder,
    user,
) -> ReminderItem:
    return ReminderItem(
        id=reminder.id,
        event=await event_list_item(session, reminder.event, user=user),
        offset_minutes=reminder.offset_minutes,
        remind_at=reminder.remind_at.isoformat(),
        status=reminder.status,
    )
