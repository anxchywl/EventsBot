from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.enums import EventStatus, ModerationAction
from app.models.event import Event, EventCategory
from app.models.moderation import ModerationLog
from app.models.user import User
from app.services.event_sync import (
    acquire_event_lock,
    capture_event_snapshot,
    enqueue_event_sync,
)
from app.services.events import (
    create_pending_event,
    get_active_categories,
    get_category_by_id,
    get_event_by_id,
    get_pending_events,
    update_event_status,
)
from app.web.flutter_auth import require_flutter_admin, require_flutter_user
from app.web.schemas import (
    FlutterCategoryItem,
    FlutterEventCreate,
    FlutterEventItem,
    FlutterEventPatch,
    FlutterEventResubmit,
    FlutterEventStatusUpdate,
)
from app.web.realtime import publish_miniapp_event, subscribe_miniapp_events
from app.web.telegram import get_web_bot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flutter/events", tags=["flutter-events"])

def _cover_url(event: Event) -> str | None:
    if not event.poster_file_id:
        return None
    return f"/api/events/{event.public_token}/cover"


# build the shared flutter event payload from a loaded event
def _serialize_event(event: Event) -> FlutterEventItem:
    return FlutterEventItem(
        id=event.id,
        public_token=event.public_token,
        title=event.title,
        description=event.description,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.strftime("%H:%M"),
        event_end_time=event.event_end_time.strftime("%H:%M") if event.event_end_time else None,
        location=event.location,
        category=event.category.name,
        organizer_name=event.organizer_name,
        status=event.status,
        cover_url=_cover_url(event),
        it_equipment=event.it_equipment,
        materials=event.materials,
        registration_url=event.registration_url,
        moderation_note=event.moderation_note,
    )


@router.get("/categories", response_model=list[FlutterCategoryItem])
async def list_categories(
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> list[FlutterCategoryItem]:
    categories = await get_active_categories(session)
    return [
        FlutterCategoryItem(id=c.id, name=c.name, slug=c.slug) for c in categories
    ]


@router.get("", response_model=list[FlutterEventItem])
async def list_events(
    search: str | None = Query(default=None, max_length=100),
    category_slug: str | None = Query(default=None, max_length=120),
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> list[FlutterEventItem]:
    stmt = (
        select(Event)
        .join(Event.category)
        .where(Event.status == EventStatus.APPROVED.value)
        .options(selectinload(Event.category))
        .order_by(Event.event_date.asc(), Event.event_time.asc())
    )

    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            func.lower(Event.title).like(func.lower(term))
            | func.lower(Event.description).like(func.lower(term))
        )
    if category_slug:
        stmt = stmt.where(EventCategory.slug == category_slug)

    result = await session.execute(stmt)
    return [_serialize_event(event) for event in result.scalars().all()]


@router.get("/my", response_model=list[FlutterEventItem])
async def list_my_events(
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> list[FlutterEventItem]:
    result = await session.execute(
        select(Event)
        .where(Event.creator_user_id == user.id)
        .options(selectinload(Event.category))
        .order_by(Event.created_at.desc())
    )
    return [_serialize_event(event) for event in result.scalars().all()]


@router.get("/pending", response_model=list[FlutterEventItem])
async def list_pending_events(
    include_rejected: bool = Query(default=False),
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> list[FlutterEventItem]:
    events = await get_pending_events(session, include_rejected=include_rejected)
    return [_serialize_event(event) for event in events]


@router.get("/updates")
async def flutter_event_updates(
    user: User = Depends(require_flutter_user),
) -> StreamingResponse:
    async def stream():
        yield ": connected\n\n"
        iterator = subscribe_miniapp_events(user.id)
        try:
            while True:
                try:
                    message = await asyncio.wait_for(anext(iterator), timeout=15.0)
                    yield f"event: {message['type']}\n"
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                except StopAsyncIteration:
                    break
        finally:
            await iterator.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{event_id}", response_model=FlutterEventItem)
async def get_event(
    event_id: int,
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> FlutterEventItem:
    event = await get_event_by_id(session, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    is_admin = user.role == "admin"
    is_approved = event.status == EventStatus.APPROVED.value
    is_owner = event.creator_user_id == user.id
    if not is_admin and not is_approved and not is_owner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    return _serialize_event(event)


@router.post("", response_model=FlutterEventItem, status_code=201)
async def submit_event(
    payload: FlutterEventCreate,
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> FlutterEventItem:
    category = await get_category_by_id(session, payload.category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    conflict = await session.scalar(
        select(Event.id)
        .where(
            Event.status == EventStatus.APPROVED.value,
            Event.event_date == payload.event_date,
            func.lower(Event.location) == func.lower(payload.location),
        )
        .limit(1)
    )
    if conflict is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This location is already booked on that date",
        )

    event_time = datetime.strptime(payload.event_time, "%H:%M").time()
    event_end_time = datetime.strptime(payload.event_end_time, "%H:%M").time()
    event = await create_pending_event(
        session,
        creator=user,
        event_data={
            "title": payload.title,
            "description": payload.description,
            "event_date": payload.event_date,
            "event_time": event_time,
            "event_end_time": event_end_time,
            "location": payload.location,
            "category_id": payload.category_id,
            "organizer": payload.organizer_name,
            "it_equipment": payload.it_equipment,
            "materials": payload.materials,
            "registration_url": payload.registration_url,
        },
    )
    await session.commit()

    created = await get_event_by_id(session, event.id)
    return _serialize_event(created)


# creator re-submits an event that was sent back for changes
@router.post("/{event_id}/resubmit", response_model=FlutterEventItem)
async def resubmit_event(
    event_id: int,
    payload: FlutterEventResubmit,
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> FlutterEventItem:
    event = await get_event_by_id(session, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    if event.creator_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    # only events sent back for changes (or already awaiting a fresh review)
    # can be resubmitted; end states and untouched submissions cannot
    if event.status not in (
        EventStatus.NEEDS_CHANGES.value,
        EventStatus.RESUBMITTED.value,
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This event cannot be resubmitted in its current state.",
        )

    # the admin notification only fires on the real state transition, not on
    # repeated resubmissions while the event is already awaiting review
    was_needs_changes = event.status == EventStatus.NEEDS_CHANGES.value

    # apply any updated fields to the existing row (no new event/draft)
    if payload.category_id is not None and payload.category_id != event.category_id:
        category = await get_category_by_id(session, payload.category_id)
        if category is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
        event.category_id = payload.category_id
    if payload.title is not None:
        event.title = payload.title
    if payload.description is not None:
        event.description = payload.description
    if payload.event_date is not None:
        event.event_date = payload.event_date
    if payload.event_time is not None:
        event.event_time = datetime.strptime(payload.event_time, "%H:%M").time()
    if payload.event_end_time is not None:
        event.event_end_time = datetime.strptime(
            payload.event_end_time, "%H:%M"
        ).time()
    if payload.location is not None:
        event.location = payload.location
    if payload.organizer_name is not None:
        event.organizer_name = payload.organizer_name
    if payload.it_equipment is not None:
        event.it_equipment = payload.it_equipment
    if payload.materials is not None:
        event.materials = payload.materials
    if payload.registration_url is not None:
        event.registration_url = payload.registration_url

    event.status = EventStatus.RESUBMITTED.value

    session.add(
        ModerationLog(
            event_id=event.id,
            actor_user_id=user.id,
            action=ModerationAction.RESUBMITTED.value,
            comment=payload.note,
        )
    )

    await session.commit()

    updated = await get_event_by_id(session, event_id)
    if was_needs_changes:
        await _notify_reviewer_of_resubmission(session, updated)
    return _serialize_event(updated)


# notify the admin who last requested changes that the creator resubmitted
async def _notify_reviewer_of_resubmission(
    session: AsyncSession, event: Event
) -> None:
    last_changes_log = await session.scalar(
        select(ModerationLog)
        .where(
            ModerationLog.event_id == event.id,
            ModerationLog.action == ModerationAction.NEEDS_CHANGES.value,
        )
        .order_by(ModerationLog.created_at.desc(), ModerationLog.id.desc())
        .limit(1)
    )
    if last_changes_log is None or last_changes_log.actor_user_id is None:
        return

    reviewer = await session.get(User, last_changes_log.actor_user_id)
    if reviewer is None or not reviewer.telegram_id:
        return

    creator_name = event.creator.first_name if event.creator else "A creator"
    try:
        await get_web_bot().send_message(
            reviewer.telegram_id,
            f"{creator_name} resubmitted {event.title}. It is ready for review.",
        )
    except Exception:
        logger.warning(
            "failed to notify reviewer of resubmission for event %s", event.id
        )


@router.patch("/{event_id}", response_model=FlutterEventItem)
async def patch_event(
    event_id: int,
    payload: FlutterEventPatch,
    user: User = Depends(require_flutter_admin),
    session: AsyncSession = Depends(get_session),
) -> FlutterEventItem:
    event = await get_event_by_id(session, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    if payload.event_end_time is not None:
        event.event_end_time = datetime.strptime(payload.event_end_time, "%H:%M").time()

    await session.commit()
    updated = await get_event_by_id(session, event_id)
    return _serialize_event(updated)


@router.patch("/{event_id}/status", response_model=FlutterEventItem)
async def moderate_event(
    event_id: int,
    payload: FlutterEventStatusUpdate,
    user: User = Depends(require_flutter_admin),
    session: AsyncSession = Depends(get_session),
) -> FlutterEventItem:
    existing = await get_event_by_id(session, event_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    new_status = EventStatus(payload.status)

    # guard against two admins moderating the same event concurrently; released
    # in the finally block once this transition is committed
    if not await _acquire_moderation_lock(event_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Another moderator is updating this event. Please try again.",
        )

    try:
        # serialize sync work for this event and freeze the currently published
        # telegram messages before the status flips, so an unpublish job can
        # still find and remove them
        await acquire_event_lock(session, event_id)
        snapshot = await capture_event_snapshot(session, event_id)

        event = await update_event_status(
            session,
            event_id,
            new_status,
            admin=user,
            comment=payload.comment,
        )

        # reuse the exact pipeline the bot uses: an "approved" job republishes
        # via edit-if-exists-else-send, every other status is delete-like and
        # unpublishes each stored EventDetailMessage. this keeps Telegram, the
        # mini app feeds/caches, and dashboards consistent with the DB status.
        await enqueue_event_sync(
            session,
            event_id=event_id,
            operation=new_status.value,
            snapshot=snapshot,
        )
        await session.commit()
    finally:
        await _release_moderation_lock(event_id)

    await publish_miniapp_event(
        "event_status_changed",
        {
            "event_id": event.id,
            "public_token": event.public_token,
            "status": event.status,
            "creator_user_id": event.creator_user_id,
        },
    )
    await _notify_creator(event)
    return _serialize_event(event)


# Redis SET NX idempotency lock mirroring _should_record_open in
# web/routers/events.py. Fails open when Redis is unavailable so a cache outage
# never hard-breaks moderation; the DB advisory lock still serializes the write.
async def _acquire_moderation_lock(event_id: int) -> bool:
    from app.db.redis import get_redis

    try:
        return bool(
            await get_redis().set(f"moderation:lock:{event_id}", "1", ex=30, nx=True)
        )
    except Exception:
        return True


async def _release_moderation_lock(event_id: int) -> None:
    from app.db.redis import get_redis

    try:
        await get_redis().delete(f"moderation:lock:{event_id}")
    except Exception:
        pass


# best-effort telegram notification, never blocking the http response
async def _notify_creator(event: Event) -> None:
    creator = event.creator
    if creator is None or creator.telegram_id == 0:
        return
    try:
        import html

        title = html.escape(event.title)
        message = _creator_status_message(title, event.status)
        # include the coordinator's comment so the submitter sees it on any
        # decision (approved / rejected / needs_changes)
        note = (event.moderation_note or "").strip()
        if note:
            message += f"\n\n<b>Coordinator comment:</b> {html.escape(note)}"
        await get_web_bot().send_message(
            creator.telegram_id,
            message,
            parse_mode="HTML",
        )
    except Exception:
        logger.warning("failed to notify creator for event %s", event.id)


def _creator_status_message(title: str, event_status: str) -> str:
    messages = {
        EventStatus.APPROVED.value: (
            f"Your event {title} has been approved and published."
        ),
        EventStatus.REJECTED.value: (
            f"Your event {title} was not approved."
        ),
        EventStatus.NEEDS_CHANGES.value: (
            f"Your event {title} needs a few edits before it can be approved."
        ),
        EventStatus.RESUBMITTED.value: (
            f"Your event {title} has been sent back for review."
        ),
        EventStatus.CANCELLED.value: (
            f"Your event {title} has been cancelled."
        ),
    }
    return messages.get(event_status, f"Your event {title} has been updated.")
