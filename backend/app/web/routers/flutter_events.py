from __future__ import annotations

import asyncio
import json
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
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
    CREATOR_CANCELLABLE_EVENT_STATUSES,
    DELETABLE_EVENT_STATUSES,
    acquire_event_submission_lock,
    apply_moderation_transition,
    can_moderate_event_status,
    create_event_update_draft,
    create_pending_event,
    delete_event_completely,
    event_effective_end_time,
    event_has_ended,
    event_submission_fingerprint,
    find_event_schedule_conflict,
    get_active_categories,
    get_category_by_id,
    get_event_by_client_request_id,
    get_event_by_id,
    get_pending_events,
    normalize_event_location,
    update_event_status,
)
from app.config import get_settings
from app.services.cover_storage import (
    CoverUploadError,
    bust_cover_cache,
    consume_and_store_cover,
    delete_stored_cover_message,
    stage_cover_bytes,
    validate_cover_bytes,
)
from app.web.flutter_auth import require_flutter_admin, require_flutter_user
from app.web.limiter import check_rate_limit
from app.web.schemas import (
    FlutterCategoryItem,
    FlutterEventCancel,
    FlutterEventCreate,
    FlutterEventItem,
    FlutterEventPatch,
    FlutterEventResubmit,
    FlutterEventStatusUpdate,
    validate_event_schedule,
    validate_event_time_range,
)
from app.web.realtime import publish_miniapp_event, subscribe_miniapp_events
from app.web.telegram import get_web_bot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flutter/events", tags=["flutter-events"])
_FLUTTER_SSE_MAX_CONNECTION_SECONDS = 300


async def _event_update_targets(
    session: AsyncSession,
    creator_user_id: int,
) -> list[int]:
    admin_ids = (
        await session.scalars(select(User.id).where(User.role == "admin"))
    ).all()
    return sorted({creator_user_id, *admin_ids})


async def _publish_event_status_change(
    session: AsyncSession,
    event: Event,
    previous_status: str,
) -> None:
    payload: dict[str, object] = {
        "event_id": event.id,
        "public_token": event.public_token,
        "status": event.status,
    }
    if (
        previous_status != EventStatus.APPROVED.value
        and event.status != EventStatus.APPROVED.value
    ):
        payload["target_user_ids"] = await _event_update_targets(
            session,
            event.creator_user_id,
        )
    await publish_miniapp_event("event_status_changed", payload)


async def _publish_event_deleted(session: AsyncSession, event: Event) -> None:
    await publish_miniapp_event(
        "event_deleted",
        {
            "event_id": event.id,
            "public_token": event.public_token,
            "target_user_ids": await _event_update_targets(
                session,
                event.creator_user_id,
            ),
        },
    )


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
        event_end_time=event.event_end_time.strftime("%H:%M")
        if event.event_end_time
        else None,
        location=event.location,
        category=event.category.name,
        organizer_name=event.organizer_name,
        status=event.status,
        cover_url=_cover_url(event),
        it_equipment=event.it_equipment,
        materials=event.materials,
        registration_url=event.registration_url,
        moderation_note=event.moderation_note,
        submitted_at=event.created_at.isoformat() if event.created_at else "",
    )


# sole trust boundary for flutter cover uploads
@router.post("/cover")
async def upload_cover(
    file: UploadFile = File(...),
    user: User = Depends(require_flutter_user),
) -> dict:
    await check_rate_limit(
        f"rate:flutter:{user.id}:cover_upload",
        30,
        3600,
        "Too many cover uploads. Please try again later.",
    )

    settings = get_settings()
    if settings.media_storage_chat_id is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Cover uploads are not configured."
        )

    # read past the limit to reject oversized uploads
    raw = await file.read(settings.media_max_upload_bytes + 1)

    try:
        # pillow work belongs off the event loop
        clean = await asyncio.to_thread(
            validate_cover_bytes, raw, file.filename, file.content_type
        )
    except CoverUploadError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    # store in telegram only after event submission
    token = await stage_cover_bytes(clean, user.id)
    return {"cover_ref": token}


# redeem a staging token without trusting client file ids. When a mutable
# `sent_messages` list is supplied, the storage-channel message id of a freshly
# sent cover is appended to it so the caller can delete the image if the
# surrounding DB transaction fails to commit.
async def _redeem_cover_ref(
    cover_ref: str, user_id: int, sent_messages: list[int] | None = None
) -> str:
    try:
        file_id = await consume_and_store_cover(
            cover_ref, user_id, sent_messages=sent_messages
        )
    except CoverUploadError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    if file_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Cover reference is invalid or expired."
        )
    return file_id


async def _apply_cover_change(
    event: Event,
    *,
    cover_ref: str | None,
    remove_cover: bool,
    user_id: int,
    sent_messages: list[int] | None = None,
) -> None:
    if remove_cover:
        if event.poster_file_id:
            await bust_cover_cache(event.poster_file_id)
        event.poster_file_id = None
        return
    if not cover_ref:
        return
    file_id = await _redeem_cover_ref(cover_ref, user_id, sent_messages)
    if event.poster_file_id and event.poster_file_id != file_id:
        await bust_cover_cache(event.poster_file_id)
    event.poster_file_id = file_id


# commit the transaction, deleting any freshly-uploaded cover images from the
# storage channel if the commit fails — otherwise the images are sent to
# Telegram but never referenced by a persisted row (orphans).
async def _commit_with_cover_cleanup(
    session: AsyncSession, sent_messages: list[int]
) -> None:
    try:
        await session.commit()
    except Exception:
        for message_id in sent_messages:
            await delete_stored_cover_message(message_id)
        raise


@router.get("/categories", response_model=list[FlutterCategoryItem])
async def list_categories(
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> list[FlutterCategoryItem]:
    categories = await get_active_categories(session)
    return [FlutterCategoryItem(id=c.id, name=c.name, slug=c.slug) for c in categories]


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
        # escape LIKE metacharacters so a search of "%%" or "____" is treated as
        # literal text, not a wildcard that scans every row at maximum cost
        escaped = (
            search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        term = f"%{escaped}%"
        stmt = stmt.where(
            func.lower(Event.title).like(func.lower(term), escape="\\")
            | func.lower(Event.description).like(func.lower(term), escape="\\")
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
    user: User = Depends(require_flutter_admin),
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
        loop = asyncio.get_running_loop()
        disconnect_at = loop.time() + _FLUTTER_SSE_MAX_CONNECTION_SECONDS
        try:
            while loop.time() < disconnect_at:
                try:
                    timeout = min(15.0, disconnect_at - loop.time())
                    message = await asyncio.wait_for(anext(iterator), timeout=timeout)
                    yield f"event: {message['type']}\n"
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    if loop.time() < disconnect_at:
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
    request_fingerprint: str | None = None
    if payload.client_request_id is not None:
        request_fingerprint = event_submission_fingerprint(
            payload.model_dump(
                mode="json",
                exclude={"client_request_id"},
            )
        )
        await acquire_event_submission_lock(
            session,
            f"event-request:{payload.client_request_id}",
        )
        existing = await get_event_by_client_request_id(
            session,
            payload.client_request_id,
        )
        if existing is not None:
            if (
                existing.creator_user_id != user.id
                or existing.client_request_fingerprint != request_fingerprint
            ):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "This event request could not be completed",
                )
            return _serialize_event(existing)

    settings = get_settings()
    await check_rate_limit(
        f"rate:flutter:{user.id}:event_submit",
        settings.flutter_event_submit_rate_limit,
        settings.flutter_event_submit_rate_window_seconds,
        "Too many event submissions. Please try again later.",
    )

    category = await get_category_by_id(session, payload.category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    event_time, event_end_time = validate_event_schedule(
        payload.event_date,
        payload.event_time,
        payload.event_end_time,
    )
    await acquire_event_submission_lock(
        session,
        "event-schedule:"
        f"{payload.event_date.isoformat()}:"
        f"{normalize_event_location(payload.location)}",
    )
    conflict = await find_event_schedule_conflict(
        session,
        event_date=payload.event_date,
        event_time=event_time,
        event_end_time=event_end_time,
        location=payload.location,
    )
    if conflict is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This location is already booked during that time",
        )

    # fail forged tokens before creating the event
    sent_covers: list[int] = []
    poster_file_id: str | None = None
    if payload.cover_ref:
        poster_file_id = await _redeem_cover_ref(
            payload.cover_ref, user.id, sent_covers
        )

    event = await create_pending_event(
        session,
        creator=user,
        event_data={
            "title": payload.title,
            "client_request_id": payload.client_request_id,
            "client_request_fingerprint": request_fingerprint,
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
            "poster_file_id": poster_file_id,
        },
    )
    await _commit_with_cover_cleanup(session, sent_covers)

    created = await get_event_by_id(session, event.id)
    return _serialize_event(created)


# creator submits corrections or a moderated update to a published event
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

    # serialize all edits to the same event before checking its current state
    await acquire_event_submission_lock(session, f"event-edit:{event.id}")
    event = await get_event_by_id(session, event_id)
    if event is None or event.creator_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    if event.status not in (
        EventStatus.NEEDS_CHANGES.value,
        EventStatus.RESUBMITTED.value,
        EventStatus.APPROVED.value,
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This event cannot be resubmitted in its current state.",
        )

    is_published_edit = event.status == EventStatus.APPROVED.value
    was_needs_changes = event.status == EventStatus.NEEDS_CHANGES.value

    request_fingerprint: str | None = None
    if payload.client_request_id is not None:
        request_fingerprint = event_submission_fingerprint(
            {
                "parent_event_id": event.id,
                **payload.model_dump(
                    mode="json",
                    exclude={"client_request_id"},
                ),
            }
        )
        await acquire_event_submission_lock(
            session,
            f"event-request:{payload.client_request_id}",
        )
        existing = await get_event_by_client_request_id(
            session,
            payload.client_request_id,
        )
        if existing is not None:
            if (
                existing.creator_user_id != user.id
                or existing.parent_event_id != event.id
                or existing.client_request_fingerprint != request_fingerprint
            ):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "This event request could not be completed",
                )
            return _serialize_event(existing)

    settings = get_settings()
    await check_rate_limit(
        f"rate:flutter:{user.id}:event_submit",
        settings.flutter_event_submit_rate_limit,
        settings.flutter_event_submit_rate_window_seconds,
        "Too many event submissions. Please try again later.",
    )

    event_date = payload.event_date or event.event_date
    event_time_value = payload.event_time or event.event_time.strftime("%H:%M")
    event_end_time_value = payload.event_end_time or (
        event.event_end_time.strftime("%H:%M") if event.event_end_time else None
    )
    if event_end_time_value is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Event end time is required",
        )
    try:
        event_time, event_end_time = validate_event_schedule(
            event_date,
            event_time_value,
            event_end_time_value,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            str(exc),
        ) from exc

    location = payload.location or event.location
    await acquire_event_submission_lock(
        session,
        f"event-schedule:{event_date.isoformat()}:{normalize_event_location(location)}",
    )
    conflict = await find_event_schedule_conflict(
        session,
        event_date=event_date,
        event_time=event_time,
        event_end_time=event_end_time,
        location=location,
        exclude_event_ids={event.id},
    )
    if conflict is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This location is already booked during that time",
        )

    category_id = payload.category_id or event.category_id
    if payload.category_id is not None:
        category = await get_category_by_id(session, category_id)
        if category is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    sent_covers: list[int] = []
    if is_published_edit:
        poster_file_id = event.poster_file_id
        if payload.remove_cover:
            poster_file_id = None
        elif payload.cover_ref:
            poster_file_id = await _redeem_cover_ref(
                payload.cover_ref,
                user.id,
                sent_covers,
            )

        draft = await create_event_update_draft(
            session,
            parent=event,
            creator=user,
            event_data={
                "title": payload.title or event.title,
                "client_request_id": payload.client_request_id,
                "client_request_fingerprint": request_fingerprint,
                "description": payload.description or event.description,
                "event_date": event_date,
                "event_time": event_time,
                "event_end_time": event_end_time,
                "location": location,
                "category_id": category_id,
                "organizer": payload.organizer_name or event.organizer_name,
                "it_equipment": payload.it_equipment
                if "it_equipment" in payload.model_fields_set
                else event.it_equipment,
                "materials": payload.materials
                if "materials" in payload.model_fields_set
                else event.materials,
                "registration_url": payload.registration_url
                if "registration_url" in payload.model_fields_set
                else event.registration_url,
                "poster_file_id": poster_file_id,
            },
        )
        await _commit_with_cover_cleanup(session, sent_covers)
        created = await get_event_by_id(session, draft.id)
        return _serialize_event(created)

    # unpublished corrections remain on the same request row
    if payload.category_id is not None:
        event.category_id = payload.category_id
    if payload.title is not None:
        event.title = payload.title
    if payload.description is not None:
        event.description = payload.description
    if payload.event_date is not None:
        event.event_date = event_date
    if payload.event_time is not None:
        event.event_time = event_time
    if payload.event_end_time is not None:
        event.event_end_time = event_end_time
    if payload.location is not None:
        event.location = payload.location
    if payload.organizer_name is not None:
        event.organizer_name = payload.organizer_name
    if "it_equipment" in payload.model_fields_set:
        event.it_equipment = payload.it_equipment
    if "materials" in payload.model_fields_set:
        event.materials = payload.materials
    if "registration_url" in payload.model_fields_set:
        event.registration_url = payload.registration_url

    await _apply_cover_change(
        event,
        cover_ref=payload.cover_ref,
        remove_cover=payload.remove_cover,
        user_id=user.id,
        sent_messages=sent_covers,
    )

    event.status = EventStatus.RESUBMITTED.value

    session.add(
        ModerationLog(
            event_id=event.id,
            actor_user_id=user.id,
            action=ModerationAction.RESUBMITTED.value,
            comment=payload.note,
        )
    )

    await _commit_with_cover_cleanup(session, sent_covers)

    updated = await get_event_by_id(session, event_id)
    if was_needs_changes:
        await _notify_reviewer_of_resubmission(session, updated)
    return _serialize_event(updated)


# notify the admin who last requested changes that the creator resubmitted
async def _notify_reviewer_of_resubmission(session: AsyncSession, event: Event) -> None:
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

    if payload.event_time is not None or payload.event_end_time is not None:
        event_time_value = payload.event_time or event.event_time.strftime("%H:%M")
        event_end_time_value = payload.event_end_time or (
            event.event_end_time.strftime("%H:%M") if event.event_end_time else None
        )
        if event_end_time_value is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Event end time is required",
            )
        try:
            event_time, event_end_time = validate_event_time_range(
                event_time_value,
                event_end_time_value,
            )
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                str(exc),
            ) from exc

        await acquire_event_submission_lock(
            session,
            "event-schedule:"
            f"{event.event_date.isoformat()}:"
            f"{normalize_event_location(event.location)}",
        )
        conflict = await find_event_schedule_conflict(
            session,
            event_date=event.event_date,
            event_time=event_time,
            event_end_time=event_end_time,
            location=event.location,
            exclude_event_id=event.id,
        )
        if conflict is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This location is already booked during that time",
            )

        event.event_time = event_time
        event.event_end_time = event_end_time

    sent_covers: list[int] = []
    await _apply_cover_change(
        event,
        cover_ref=payload.cover_ref,
        remove_cover=payload.remove_cover,
        user_id=user.id,
        sent_messages=sent_covers,
    )

    await _commit_with_cover_cleanup(session, sent_covers)
    updated = await get_event_by_id(session, event_id)
    return _serialize_event(updated)


@router.post("/{event_id}/cancel", response_model=FlutterEventItem)
async def cancel_event(
    event_id: int,
    payload: FlutterEventCancel,
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> FlutterEventItem:
    existing = await get_event_by_id(session, event_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if existing.creator_user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    await acquire_event_lock(session, event_id)
    current = await get_event_by_id(session, event_id)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if current.creator_user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if current.status == EventStatus.CANCELLED.value:
        return _serialize_event(current)
    if current.status not in CREATOR_CANCELLABLE_EVENT_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This event cannot be cancelled in its current state.",
        )

    previous_status = current.status
    snapshot = await capture_event_snapshot(session, event_id)
    event = await update_event_status(
        session,
        event_id,
        EventStatus.CANCELLED,
        user,
        payload.comment,
    )
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    await enqueue_event_sync(
        session,
        event_id=event_id,
        operation=EventStatus.CANCELLED.value,
        snapshot=snapshot,
    )
    await session.commit()

    await _publish_event_status_change(session, event, previous_status)
    await _notify_creator(event)
    return _serialize_event(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
    user: User = Depends(require_flutter_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    existing = await get_event_by_id(session, event_id)
    if existing is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if existing.creator_user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if existing.status not in DELETABLE_EVENT_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cancel the event before deleting it.",
        )

    deleted = await delete_event_completely(
        session,
        bot=None,
        event_id=event_id,
        allowed_statuses=DELETABLE_EVENT_STATUSES,
    )
    if not deleted:
        current = await session.get(Event, event_id)
        if current is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This event cannot be deleted in its current state.",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    await session.commit()
    await _publish_event_deleted(session, existing)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    lock_event_id = existing.parent_event_id or existing.id

    if not await _acquire_moderation_lock(lock_event_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Another moderator is updating this event. Please try again.",
        )

    try:
        await acquire_event_lock(session, lock_event_id)
        current = await get_event_by_id(session, event_id)
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

        previous_status = current.status
        if not can_moderate_event_status(previous_status, new_status):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This event cannot move to that status.",
            )

        if new_status == EventStatus.APPROVED:
            if event_has_ended(current):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Past events cannot be approved.",
                )
            await acquire_event_submission_lock(
                session,
                "event-schedule:"
                f"{current.event_date.isoformat()}:"
                f"{normalize_event_location(current.location)}",
            )
            excluded_ids = {current.id}
            if current.parent_event_id is not None:
                excluded_ids.add(current.parent_event_id)
            conflict = await find_event_schedule_conflict(
                session,
                event_date=current.event_date,
                event_time=current.event_time,
                event_end_time=event_effective_end_time(current),
                location=current.location,
                exclude_event_ids=excluded_ids,
            )
            if conflict is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "This location is already booked during that time",
                )

        sync_event_id = (
            current.parent_event_id
            if new_status == EventStatus.APPROVED
            and current.parent_event_id is not None
            else current.id
        )
        snapshot = await capture_event_snapshot(session, sync_event_id)
        try:
            event = await apply_moderation_transition(
                session,
                current,
                new_status,
                user,
                payload.comment,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

        await enqueue_event_sync(
            session,
            event_id=event.id,
            operation=new_status.value,
            snapshot=snapshot,
        )
        await session.commit()
    finally:
        await _release_moderation_lock(lock_event_id)

    if event.id != event_id:
        await _publish_event_deleted(session, existing)
    await _publish_event_status_change(session, event, previous_status)
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
        EventStatus.REJECTED.value: (f"Your event {title} was not approved."),
        EventStatus.NEEDS_CHANGES.value: (
            f"Your event {title} needs a few edits before it can be approved."
        ),
        EventStatus.RESUBMITTED.value: (
            f"Your event {title} has been sent back for review."
        ),
        EventStatus.CANCELLED.value: (f"Your event {title} has been cancelled."),
    }
    return messages.get(event_status, f"Your event {title} has been updated.")
