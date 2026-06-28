from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.web.limiter import check_rate_limit
from app.web.routers.events import event_cache, validate_public_token
from app.web.schemas import ActionResponse, ReminderGroup, ReminderItem, ReminderRequest
from app.web.serializers import event_list_item


router = APIRouter(tags=["miniapp-reminders"])


# group scheduled reminders by event
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


# create or replace one event reminder
@router.post("/api/events/{public_token}/reminders", response_model=ActionResponse)
async def create_reminder(
    public_token: str,
    payload: ReminderRequest,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    await check_rate_limit(f"rate:user:{user.id}:reminder", 20, 3600, "Too many reminder attempts. Try again later.")
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
    return ActionResponse(ok=True, message="Reminder set.")


# delete a reminder owned by the current user
@router.delete("/api/reminders/{reminder_id}", response_model=ActionResponse)
async def delete_reminder(
    reminder_id: int,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    await check_rate_limit(f"rate:user:{user.id}:reminder_delete", 50, 3600, "Too many requests. Try again later.")
    event_id = await cancel_reminder(session, user, reminder_id)
    if event_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found.")
    await session.commit()
    event_cache.clear()
    return ActionResponse(ok=True, message="Reminder removed.")


# serialize reminder metadata for the mini app
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
