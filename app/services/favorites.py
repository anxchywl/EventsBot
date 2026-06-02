from __future__ import annotations

from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event
from app.models.enums import EventStatus
from app.models.favorite import Favorite
from app.models.user import User


async def is_event_favorite(session: AsyncSession, user: User | None, event_id: int) -> bool:
    if not user:
        return False
    favorite_id = await session.scalar(
        select(Favorite.id).where(
            Favorite.user_id == user.id,
            Favorite.event_id == event_id,
        )
    )
    return favorite_id is not None


async def get_favorite_event_ids(
    session: AsyncSession,
    user: User | None,
    event_ids: Sequence[int],
) -> set[int]:
    if not user or not event_ids:
        return set()
    result = await session.execute(
        select(Favorite.event_id).where(
            Favorite.user_id == user.id,
            Favorite.event_id.in_(event_ids),
        )
    )
    return set(result.scalars().all())


async def add_favorite(session: AsyncSession, user: User, event: Event) -> bool:
    if await is_event_favorite(session, user, event.id):
        return False
    session.add(Favorite(user_id=user.id, event_id=event.id))
    from sqlalchemy.exc import IntegrityError
    try:
        await session.flush()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def remove_favorite(session: AsyncSession, user: User, event: Event) -> bool:
    result = await session.execute(
        delete(Favorite)
        .where(Favorite.user_id == user.id, Favorite.event_id == event.id)
        .returning(Favorite.id)
    )
    return result.scalar_one_or_none() is not None


async def get_user_favorite_events(session: AsyncSession, user: User) -> Sequence[Event]:
    result = await session.execute(
        select(Event)
        .join(Favorite, Favorite.event_id == Event.id)
        .where(
            Favorite.user_id == user.id,
            Event.status == EventStatus.APPROVED.value,
        )
        .order_by(Event.event_date, Event.event_time)
        .options(selectinload(Event.category))
    )
    return result.scalars().all()
