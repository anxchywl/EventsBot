from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.user import User
from app.models.event import Event
from app.models.enums import EventStatus
from app.models.rating import Rating
from app.models.comment import Comment
from app.services.events import get_event_by_public_token
from app.services.friends import avatar_payload
from app.services.reviews import invalidate_review_caches, permanently_delete_review
from app.web.realtime import publish_review_deleted
from app.web.auth import (
    MiniAppUser,
    effective_web_role,
    optional_current_miniapp_user,
    require_current_miniapp_user,
    require_verified_user,
    require_verified_user_allow_blocked,
    upsert_miniapp_user,
)
from app.web.routers.events import validate_public_token
from app.web.schemas import FeedReviewDetail, ReviewSubmitRequest, ActionResponse, ReviewDetail

logger = logging.getLogger("app.web.routers.ratings")
router = APIRouter(prefix="/api/events", tags=["ratings-reviews"])
_CONTROL_CHARS_RE = re.compile(r'[\u200b-\u200d\uFEFF\u200e\u200f\u202a-\u202e\x00-\x1f\x7f-\x9f]')
_WHITESPACE_RE = re.compile(r"\s+")

_RATING_RATE_LIMITS: dict[str, list[float]] = {}

# limit review actions in memory
def _check_rate_limit(request: Request, user_id: int, limit: int, window_seconds: int) -> None:
    import time
    now = time.time()
    cutoff = now - window_seconds
    host = request.client.host if request.client else "unknown"
    key = f"review:{user_id}:{host}"
    hits = [ts for ts in _RATING_RATE_LIMITS.get(key, []) if ts > cutoff]

    # prevent memory leaks by pruning stale keys when dict grows large
    if len(_RATING_RATE_LIMITS) > 10000:
        for k in list(_RATING_RATE_LIMITS.keys()):
            _RATING_RATE_LIMITS[k] = [ts for ts in _RATING_RATE_LIMITS[k] if ts > cutoff]
            if not _RATING_RATE_LIMITS[k]:
                del _RATING_RATE_LIMITS[k]

    if len(hits) >= limit:
        _RATING_RATE_LIMITS[key] = hits
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try again later.")
    hits.append(now)
    _RATING_RATE_LIMITS[key] = hits
@router.post("/{public_token}/reviews", response_model=ActionResponse)
async def submit_review(
    public_token: str,
    payload: ReviewSubmitRequest,
    request: Request,
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    _check_rate_limit(request, user.id, limit=5, window_seconds=60)
    public_token = validate_public_token(public_token)
    event = await get_event_by_public_token(session, public_token)
    if not event or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    score = payload.score
    content_raw = payload.content
    content = None

    if content_raw is not None and content_raw != "":
        if not content_raw.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Comments consisting only of spaces are invalid."
            )
        
        # strip hidden unicode formatting before storing comments
        cleaned = _CONTROL_CHARS_RE.sub('', content_raw)
        cleaned = _WHITESPACE_RE.sub(' ', cleaned).strip()
        
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Comment contains only invalid or hidden characters."
            )
            
        if len(cleaned) > 256:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Comment cannot exceed 256 characters."
            )
        
        # reject script-like content after normalization
        if "<script" in cleaned.lower() or "javascript:" in cleaned.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Script injection detected in comment."
            )
            
        content = cleaned

    if score is None and not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either a rating score or a comment."
        )

    if score is not None:
        stmt = select(Rating).where(Rating.user_id == user.id, Rating.event_id == event.id)
        existing_rating = (await session.execute(stmt)).scalar_one_or_none()
        if existing_rating:
            existing_rating.score = score
            existing_rating.deleted_at = None
            existing_rating.deleted_by_user_id = None
            existing_rating.delete_reason = None
        else:
            db_rating = Rating(user_id=user.id, event_id=event.id, score=score)
            session.add(db_rating)

    if content:
        stmt = select(Comment).where(Comment.user_id == user.id, Comment.event_id == event.id)
        existing_comment = (await session.execute(stmt)).scalar_one_or_none()
        if existing_comment:
            existing_comment.content = content
            existing_comment.deleted_at = None
            existing_comment.deleted_by_user_id = None
            existing_comment.delete_reason = None
        else:
            db_comment = Comment(user_id=user.id, event_id=event.id, content=content)
            session.add(db_comment)

    await session.commit()
    invalidate_review_caches()
    return ActionResponse(ok=True, message="Review submitted successfully.")


# delete the current user review for one event
@router.delete("/{public_token}/reviews", response_model=ActionResponse)
async def delete_review(
    public_token: str,
    user: User = Depends(require_verified_user_allow_blocked),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    public_token = validate_public_token(public_token)
    event = await get_event_by_public_token(session, public_token)
    if not event or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    await session.execute(
        delete(Rating).where(Rating.user_id == user.id, Rating.event_id == event.id)
    )
    await session.execute(
        delete(Comment).where(Comment.user_id == user.id, Comment.event_id == event.id)
    )

    await session.commit()
    invalidate_review_caches()
    return ActionResponse(ok=True, message="Review deleted successfully.")


# list merged ratings and comments for an event
@router.get("/{public_token}/reviews", response_model=list[ReviewDetail])
async def list_reviews(
    public_token: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=5000),
    miniapp_user: MiniAppUser | None = Depends(optional_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[ReviewDetail]:
    public_token = validate_public_token(public_token)
    event = await get_event_by_public_token(session, public_token)
    if not event or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    current_db_user = None
    if miniapp_user:
        current_db_user = await upsert_miniapp_user(session, miniapp_user)

    stmt = select(Rating).where(Rating.event_id == event.id, Rating.deleted_at.is_(None)).options(selectinload(Rating.user))
    ratings = (await session.execute(stmt)).scalars().all()

    stmt = select(Comment).where(Comment.event_id == event.id, Comment.deleted_at.is_(None)).options(selectinload(Comment.user))
    comments = (await session.execute(stmt)).scalars().all()

    can_delete_all = False
    if current_db_user and miniapp_user:
        current_role = effective_web_role(current_db_user, miniapp_user.id)
        if current_role in ("admin", "moderator"):
            can_delete_all = True

    # merge one user rating and comment into one review row
    user_map: dict[int, dict] = {}
    
    for r in ratings:
        if not r.user.is_verified:
            continue
        user_map[r.user_id] = {
            "comment_id": None,
            "rating_id": r.id if can_delete_all else None,
            "nickname": r.user.nickname or "Anonymous",
            "avatar": avatar_payload(r.user),
            "content": None,
            "score": r.score,
            "created_at": r.created_at.isoformat(),
            "is_own": current_db_user is not None and r.user_id == current_db_user.id,
            "can_delete": can_delete_all,
            "user_id": r.user_id if can_delete_all else None,
        }

    for c in comments:
        if not c.user.is_verified:
            continue
        if c.user_id in user_map:
            user_map[c.user_id]["comment_id"] = c.id if can_delete_all else None
            user_map[c.user_id]["content"] = c.content
        else:
            user_map[c.user_id] = {
                "comment_id": c.id if can_delete_all else None,
                "rating_id": None,
                "nickname": c.user.nickname or "Anonymous",
                "avatar": avatar_payload(c.user),
                "content": c.content,
                "score": None,
                "created_at": c.created_at.isoformat(),
                "is_own": current_db_user is not None and c.user_id == current_db_user.id,
                "can_delete": can_delete_all,
                "user_id": c.user_id if can_delete_all else None,
            }

    # keep the current user review visible first
    reviews = list(user_map.values())
    reviews.sort(key=lambda x: (not x["is_own"], x["created_at"]), reverse=True)

    return [ReviewDetail(**val) for val in reviews[offset : offset + limit]]


# list recent verified reviews across events
@router.get("/reviews/feed", response_model=list[FeedReviewDetail])
async def list_global_reviews_feed(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=5000),
    miniapp_user: MiniAppUser | None = Depends(optional_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[FeedReviewDetail]:
    current_db_user = None
    can_delete_all = False
    if miniapp_user is not None:
        current_db_user = await upsert_miniapp_user(session, miniapp_user)
        can_delete_all = effective_web_role(current_db_user, miniapp_user.id) in ("admin", "moderator")

    stmt_comments = (
        select(Comment)
        .join(Comment.user)
        .join(Comment.event)
        .where(User.is_verified, Event.status == "approved", Comment.deleted_at.is_(None))
        .order_by(Comment.created_at.desc())
        .options(selectinload(Comment.user), selectinload(Comment.event))
        .offset(offset)
        .limit(limit)
    )
    comments = (await session.execute(stmt_comments)).scalars().all()

    stmt_ratings = (
        select(Rating)
        .join(Rating.user)
        .join(Rating.event)
        .where(User.is_verified, Event.status == "approved", Rating.deleted_at.is_(None))
        .order_by(Rating.created_at.desc())
        .options(selectinload(Rating.user), selectinload(Rating.event))
        .offset(offset)
        .limit(limit)
    )
    ratings = (await session.execute(stmt_ratings)).scalars().all()

    # merge each user and event into one feed review row
    feed_map = {}
    for r in ratings:
        key = (r.user_id, r.event_id)
        feed_map[key] = {
            "event_token": r.event.public_token,
            "event_title": r.event.title,
            "nickname": r.user.nickname or "Anonymous",
            "content": None,
            "score": r.score,
            "created_at": r.created_at.isoformat(),
            "user_id": r.user_id if can_delete_all else None,
            "rating_id": r.id if can_delete_all else None,
            "comment_id": None,
        }

    for c in comments:
        key = (c.user_id, c.event_id)
        if key in feed_map:
            feed_map[key]["content"] = c.content
            try:
                c_date = c.created_at.isoformat()
                if c_date > feed_map[key]["created_at"]:
                    feed_map[key]["created_at"] = c_date
            except Exception:
                pass
        else:
            feed_map[key] = {
                "event_token": c.event.public_token,
                "event_title": c.event.title,
                "nickname": c.user.nickname or "Anonymous",
                "content": c.content,
                "score": None,
                "created_at": c.created_at.isoformat(),
                "user_id": c.user_id if can_delete_all else None,
                "comment_id": c.id if can_delete_all else None,
                "rating_id": None,
            }

    feed = list(feed_map.values())
    feed.sort(key=lambda x: x["created_at"], reverse=True)
    return [FeedReviewDetail(**val) for val in feed[:limit]]


# allow admins to remove reviews by event token
@router.delete("/admin/{public_token}/reviews/{target_user_id}", response_model=ActionResponse)
async def admin_delete_review(
    public_token: str,
    target_user_id: int,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    public_token = validate_public_token(public_token)
    user = await upsert_miniapp_user(session, miniapp_user)
    if effective_web_role(user, miniapp_user.id) not in ("admin", "moderator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    event = await get_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    result = await permanently_delete_review(
        session,
        event=event,
        target_user_id=target_user_id,
        admin=user,
    )
    if not result["deleted"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review already deleted")
    await session.commit()
    invalidate_review_caches()
    await publish_review_deleted(result)
    return ActionResponse(ok=True, message="Review deleted by admin.")
