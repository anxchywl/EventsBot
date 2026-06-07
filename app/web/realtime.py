from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any


_subscribers: set[tuple[int | None, asyncio.Queue[dict[str, Any]]]] = set()


async def publish_miniapp_event(event_type: str, payload: dict[str, Any]) -> None:
    message = {"type": event_type, **payload}
    target_user_ids = {
        int(user_id)
        for user_id in payload.get("target_user_ids", []) or []
        if user_id is not None
    }
    stale: list[tuple[int | None, asyncio.Queue[dict[str, Any]]]] = []
    for user_id, queue in tuple(_subscribers):
        if target_user_ids and user_id not in target_user_ids:
            continue
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            stale.append((user_id, queue))
    for subscriber in stale:
        _subscribers.discard(subscriber)


async def publish_review_deleted(payload: dict[str, Any]) -> None:
    public_payload = {
        key: payload[key]
        for key in (
            "deleted",
            "event_token",
            "average_rating",
            "rating_count",
            "rating_distribution",
            "review_count",
            "deleted_at",
        )
        if key in payload
    }
    await publish_miniapp_event("review_deleted", public_payload)


async def subscribe_miniapp_events(user_id: int | None = None) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=20)
    subscriber = (user_id, queue)
    _subscribers.add(subscriber)
    try:
        while True:
            yield await queue.get()
    finally:
        with suppress(KeyError):
            _subscribers.remove(subscriber)
