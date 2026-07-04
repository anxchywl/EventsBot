from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.enums import EventStatus
from app.models.event import Event, EventCategory
from app.models.user import User
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
    FlutterEventStatusUpdate,
)
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
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> list[FlutterEventItem]:
    events = await get_pending_events(session)
    return [_serialize_event(event) for event in events]


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

    event = await update_event_status(
        session,
        event_id,
        EventStatus(payload.status),
        admin=user,
        comment=payload.comment,
    )
    await session.commit()

    await _notify_creator(event)
    return _serialize_event(event)


# best-effort telegram notification, never blocking the http response
async def _notify_creator(event: Event) -> None:
    creator = event.creator
    if creator is None or creator.telegram_id == 0:
        return
    try:
        await get_web_bot().send_message(
            creator.telegram_id,
            f"Your event '{event.title}' was updated: {event.status}",
        )
    except Exception:
        logger.warning("failed to notify creator for event %s", event.id)
