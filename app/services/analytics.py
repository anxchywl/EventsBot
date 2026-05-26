from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import EventAnalytics
from app.models.event import Event
from app.models.user import User

logger = logging.getLogger(__name__)


async def record_event_action(
    session: AsyncSession,
    *,
    event: Event,
    action: str,
    user: User | None = None,
    source: str | None = None,
    chat_id: int | None = None,
) -> None:
    session.add(
        EventAnalytics(
            event_id=event.id,
            user_id=user.id if user else None,
            action=action,
            source=source,
            chat_id=chat_id,
        )
    )
    logger.info(
        "event action",
        extra={
            "event_id": event.id,
            "public_token": event.public_token,
            "action": action,
            "user_id": user.id if user else None,
            "source": source,
            "chat_id": chat_id,
        },
    )


async def record_event_action_by_ids(
    session: AsyncSession,
    *,
    event_id: int,
    action: str,
    user_id: int | None = None,
    source: str | None = None,
    chat_id: int | None = None,
) -> None:
    session.add(
        EventAnalytics(
            event_id=event_id,
            user_id=user_id,
            action=action,
            source=source,
            chat_id=chat_id,
        )
    )
    logger.info(
        "event action",
        extra={
            "event_id": event_id,
            "action": action,
            "user_id": user_id,
            "source": source,
            "chat_id": chat_id,
        },
    )
