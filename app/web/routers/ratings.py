from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.user import User
from app.models.event import Event
from app.models.rating import Rating
from app.models.comment import Comment
from app.services.events import get_event_by_public_token
from app.services.friends import avatar_payload
from app.services.reviews import invalidate_review_caches, permanently_delete_review
from app.web.realtime import publish_review_deleted
from app.web.auth import (
    MiniAppUser,
    effective_web_role,
    optional_miniapp_user,
    require_current_miniapp_user,
    require_verified_user,
    require_verified_user_allow_blocked,
    upsert_miniapp_user,
)
from app.web.schemas import ReviewSubmitRequest, ActionResponse, ReviewDetail

logger = logging.getLogger("app.web.routers.ratings")
router = APIRouter(prefix="/api/events", tags=["ratings-reviews"])


@router.post("/{public_token}/reviews", response_model=ActionResponse)
async def submit_review(
    public_token: str,
    payload: ReviewSubmitRequest,
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    event = await get_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    score = payload.score
    content_raw = payload.content
    content = None

    if content_raw is not None and content_raw != "":
        # Check if empty or consisting only of spaces
        if not content_raw.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Comments consisting only of spaces are invalid."
            )
        
        import re
        # Clean hidden formatting / control characters (Cc, Cf, Cs, Co, Cn)
        cleaned = re.sub(r'[\u200b-\u200d\uFEFF\u200e\u200f\u202a-\u202e\x00-\x1f\x7f-\x9f]', '', content_raw)
        # Normalize consecutive spaces, tabs, and newlines to a single space
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
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
        
        # Script protection extra check
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

    # 1. Handle Rating
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

    # 2. Handle Comment
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


@router.delete("/{public_token}/reviews", response_model=ActionResponse)
async def delete_review(
    public_token: str,
    user: User = Depends(require_verified_user_allow_blocked),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    event = await get_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Delete rating
    await session.execute(
        delete(Rating).where(Rating.user_id == user.id, Rating.event_id == event.id)
    )
    # Delete comment
    await session.execute(
        delete(Comment).where(Comment.user_id == user.id, Comment.event_id == event.id)
    )

    await session.commit()
    invalidate_review_caches()
    return ActionResponse(ok=True, message="Review deleted successfully.")


@router.get("/{public_token}/reviews", response_model=list[ReviewDetail])
async def list_reviews(
    public_token: str,
    miniapp_user: MiniAppUser | None = Depends(optional_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[ReviewDetail]:
    event = await get_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    current_db_user = None
    if miniapp_user:
        current_db_user = await upsert_miniapp_user(session, miniapp_user)

    # Fetch ratings
    stmt = select(Rating).where(Rating.event_id == event.id, Rating.deleted_at.is_(None)).options(selectinload(Rating.user))
    ratings = (await session.execute(stmt)).scalars().all()

    # Fetch comments
    stmt = select(Comment).where(Comment.event_id == event.id, Comment.deleted_at.is_(None)).options(selectinload(Comment.user))
    comments = (await session.execute(stmt)).scalars().all()

    can_delete_all = False
    if current_db_user and miniapp_user:
        current_role = effective_web_role(current_db_user, miniapp_user.id)
        if current_role in ("admin", "moderator"):
            can_delete_all = True

    # Merge ratings and comments by user_id
    user_map: dict[int, dict] = {}
    
    # Process ratings
    for r in ratings:
        if not r.user.is_verified:
            continue
        user_map[r.user_id] = {
            "comment_id": None,
            "rating_id": r.id,
            "nickname": r.user.nickname or "Anonymous",
            "avatar": avatar_payload(r.user),
            "content": None,
            "score": r.score,
            "created_at": r.created_at.isoformat(),
            "is_own": current_db_user is not None and r.user_id == current_db_user.id,
            "can_delete": can_delete_all,
            "user_id": r.user_id
        }

    # Process comments
    for c in comments:
        if not c.user.is_verified:
            continue
        if c.user_id in user_map:
            user_map[c.user_id]["comment_id"] = c.id
            user_map[c.user_id]["content"] = c.content
        else:
            user_map[c.user_id] = {
                "comment_id": c.id,
                "rating_id": None,
                "nickname": c.user.nickname or "Anonymous",
                "avatar": avatar_payload(c.user),
                "content": c.content,
                "score": None,
                "created_at": c.created_at.isoformat(),
                "is_own": current_db_user is not None and c.user_id == current_db_user.id,
                "can_delete": can_delete_all,
                "user_id": c.user_id
            }

    # Sort reviews so the current user's review is first, followed by newest
    reviews = list(user_map.values())
    reviews.sort(key=lambda x: (not x["is_own"], x["created_at"]), reverse=True)

    return [ReviewDetail(**val) for val in reviews]


from pydantic import BaseModel

class FeedReviewDetail(BaseModel):
    event_token: str
    event_title: str
    nickname: str
    content: str | None = None
    score: int | None = None
    created_at: str
    user_id: int | None = None
    comment_id: int | None = None
    rating_id: int | None = None


@router.get("/reviews/feed", response_model=list[FeedReviewDetail])
async def list_global_reviews_feed(
    session: AsyncSession = Depends(get_session),
) -> list[FeedReviewDetail]:
    # Query 20 most recent comments and ratings from verified users
    stmt_comments = (
        select(Comment)
        .join(Comment.user)
        .join(Comment.event)
        .where(User.is_verified == True, Event.status == "approved", Comment.deleted_at.is_(None))
        .order_by(Comment.created_at.desc())
        .options(selectinload(Comment.user), selectinload(Comment.event))
        .limit(20)
    )
    comments = (await session.execute(stmt_comments)).scalars().all()

    stmt_ratings = (
        select(Rating)
        .join(Rating.user)
        .join(Rating.event)
        .where(User.is_verified == True, Event.status == "approved", Rating.deleted_at.is_(None))
        .order_by(Rating.created_at.desc())
        .options(selectinload(Rating.user), selectinload(Rating.event))
        .limit(20)
    )
    ratings = (await session.execute(stmt_ratings)).scalars().all()

    # Merge ratings and comments by (user_id, event_id)
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
            "user_id": r.user_id,
            "rating_id": r.id,
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
                "user_id": c.user_id,
                "comment_id": c.id,
                "rating_id": None,
            }

    # Sort merged list by created_at desc, limit 20
    feed = list(feed_map.values())
    feed.sort(key=lambda x: x["created_at"], reverse=True)
    return [FeedReviewDetail(**val) for val in feed[:20]]


@router.delete("/admin/{public_token}/reviews/{target_user_id}", response_model=ActionResponse)
async def admin_delete_review(
    public_token: str,
    target_user_id: int,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
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
