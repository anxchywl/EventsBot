from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.comment import Comment
from app.models.event import Event
from app.models.rating import Rating
from app.models.user import User


# delete review data and invalidate derived caches
async def permanently_delete_review(
    session: AsyncSession,
    *,
    event: Event,
    target_user_id: int | None = None,
    rating_id: int | None = None,
    comment_id: int | None = None,
    admin: User,
) -> dict[str, Any]:
    """Permanently delete review data for an event and record moderation history."""
    if target_user_id is None:
        target_user_id = await _resolve_review_user_id(
            session,
            event_id=event.id,
            rating_id=rating_id,
            comment_id=comment_id,
        )

    if target_user_id is None:
        return _not_deleted_result(event)

    rating_ids = list(
        (
            await session.execute(
                select(Rating.id).where(
                    Rating.event_id == event.id,
                    Rating.user_id == target_user_id,
                )
            )
        ).scalars()
    )
    comment_ids = list(
        (
            await session.execute(
                select(Comment.id).where(
                    Comment.event_id == event.id,
                    Comment.user_id == target_user_id,
                )
            )
        ).scalars()
    )

    if not rating_ids and not comment_ids:
        return _not_deleted_result(event, target_user_id=target_user_id)

    await session.execute(
        delete(Rating).where(
            Rating.event_id == event.id,
            Rating.user_id == target_user_id,
        )
    )
    await session.execute(
        delete(Comment).where(
            Comment.event_id == event.id,
            Comment.user_id == target_user_id,
        )
    )

    deleted_at = datetime.now(UTC)
    summary = await event_rating_summary(session, event.id)
    session.add(
        AuditLog(
            actor_user_id=admin.id,
            action="delete_review",
            target_type="review",
            target_id=f"{event.id}:{target_user_id}",
            metadata_json={
                "admin_id": admin.id,
                "admin_username": admin.username,
                "deleted_review_id": {
                    "rating_ids": rating_ids,
                    "comment_ids": comment_ids,
                },
                "event_id": event.id,
                "event_token": event.public_token,
                "target_user_id": target_user_id,
                "timestamp": deleted_at.isoformat(),
            },
        )
    )

    return {
        "deleted": True,
        "event_id": event.id,
        "event_token": event.public_token,
        "target_user_id": target_user_id,
        "rating_ids": rating_ids,
        "comment_ids": comment_ids,
        "average_rating": summary["average_rating"],
        "rating_count": summary["rating_count"],
        "rating_distribution": summary["rating_distribution"],
        "review_count": summary["review_count"],
        "deleted_at": deleted_at.isoformat(),
    }


# resolve review ownership from verified or telegram identity
async def _resolve_review_user_id(
    session: AsyncSession,
    *,
    event_id: int,
    rating_id: int | None,
    comment_id: int | None,
) -> int | None:
    if rating_id is not None:
        user_id = await session.scalar(
            select(Rating.user_id).where(
                Rating.event_id == event_id, Rating.id == rating_id
            )
        )
        if user_id is not None:
            return int(user_id)
    if comment_id is not None:
        user_id = await session.scalar(
            select(Comment.user_id).where(
                Comment.event_id == event_id, Comment.id == comment_id
            )
        )
        if user_id is not None:
            return int(user_id)
    return None


# return a stable result when no review existed
def _not_deleted_result(
    event: Event, *, target_user_id: int | None = None
) -> dict[str, Any]:
    return {
        "deleted": False,
        "event_id": event.id,
        "event_token": event.public_token,
        "target_user_id": target_user_id,
        "rating_ids": [],
        "comment_ids": [],
    }


# combine rating aggregates with current user review state
async def event_rating_summary(session: AsyncSession, event_id: int) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(Rating.score, func.count(Rating.id))
            .join(Rating.user)
            .where(
                Rating.event_id == event_id,
                Rating.deleted_at.is_(None),
                User.is_verified == True,
            )
            .group_by(Rating.score)
        )
    ).all()
    distribution = {str(score): 0 for score in range(1, 6)}
    rating_total = 0
    rating_sum = 0
    for score, count in rows:
        score_int = int(score)
        count_int = int(count or 0)
        distribution[str(score_int)] = count_int
        rating_total += count_int
        rating_sum += score_int * count_int

    reviewed_user_rows = (
        await session.execute(
            select(Rating.user_id)
            .join(Rating.user)
            .where(
                Rating.event_id == event_id,
                Rating.deleted_at.is_(None),
                User.is_verified == True,
            )
            .union(
                select(Comment.user_id)
                .join(Comment.user)
                .where(
                    Comment.event_id == event_id,
                    Comment.deleted_at.is_(None),
                    User.is_verified == True,
                )
            )
        )
    ).all()

    return {
        "average_rating": (rating_sum / rating_total) if rating_total else None,
        "rating_count": rating_total,
        "rating_distribution": distribution,
        "review_count": len(reviewed_user_rows),
    }


# clear cached event data after review changes
def invalidate_review_caches() -> None:
    from app.web.routers.events import event_cache

    event_cache.clear()
