from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any


_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()


async def publish_review_deleted(payload: dict[str, Any]) -> None:
    message = {"type": "review_deleted", **payload}
    stale: list[asyncio.Queue[dict[str, Any]]] = []
    for queue in tuple(_subscribers):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            stale.append(queue)
    for queue in stale:
        _subscribers.discard(queue)


async def subscribe_miniapp_events() -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=20)
    _subscribers.add(queue)
    try:
        while True:
            yield await queue.get()
    finally:
        with suppress(KeyError):
            _subscribers.remove(queue)
