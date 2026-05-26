from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.reminder import Reminder
from app.services.events import get_available_event_by_public_token
from app.services.reminders import (
    cancel_reminder,
    get_user_scheduled_reminders,
    schedule_reminder_offset,
)
from app.web.auth import MiniAppUser, require_miniapp_user, upsert_miniapp_user
from app.web.schemas import ActionResponse, ReminderGroup, ReminderItem, ReminderRequest
from app.web.serializers import event_list_item


router = APIRouter(tags=["miniapp-reminders"])


@router.get("/api/reminders", response_model=list[ReminderGroup])
async def list_reminders(
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[ReminderGroup]:
    user = await upsert_miniapp_user(session, miniapp_user)
    reminders = await get_user_scheduled_reminders(session, user)
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
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    event = await get_available_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event no longer available")

    try:
        await schedule_reminder_offset(session, user, event, payload.offset_minutes)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await session.commit()
    return ActionResponse(message="Reminder set.")


@router.delete("/api/reminders/{reminder_id}", response_model=ActionResponse)
async def delete_reminder(
    reminder_id: int,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    event_id = await cancel_reminder(session, user, reminder_id)
    if event_id is None:
        await session.commit()
        return ActionResponse(message="Reminder removed.")
    await session.commit()
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
