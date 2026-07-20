from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any


# In-process fan-out registry. This is correct for the current single-uvicorn
# deployment (one event loop, no --workers). Scaling to multiple workers or hosts
# would require a shared broker (e.g. Redis pub/sub) so a publish on one process
# reaches subscribers on another — until then, horizontal scale is the ceiling.
_subscribers: set[tuple[int | None, asyncio.Queue[dict[str, Any]]]] = set()

# Coalesced analytics-invalidation signal. A firehose of views/clicks must not
# fan a per-write SSE out to every connected coordinator, so writes are debounced
# into a single "these metrics changed" hint every _ANALYTICS_DEBOUNCE_SECONDS.
# The payload carries only action names (no counts, ids or PII) — the client uses
# it purely to decide which dashboard panels to refetch authoritative aggregates
# for. The bounded fallback poll reconciles anything a coalesced flush misses.
_ANALYTICS_DEBOUNCE_SECONDS = 5.0
_pending_analytics_metrics: set[str] = set()
_analytics_flush_task: asyncio.Task[None] | None = None


def schedule_analytics_changed(*metrics: str) -> None:
    global _analytics_flush_task
    for metric in metrics:
        if metric:
            _pending_analytics_metrics.add(metric)
    if not _pending_analytics_metrics:
        return
    if _analytics_flush_task is not None and not _analytics_flush_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # no running loop (sync context / tests): drop the hint, the client poll
        # still reconciles
        _pending_analytics_metrics.clear()
        return
    _analytics_flush_task = loop.create_task(_flush_analytics_changed())


async def _flush_analytics_changed() -> None:
    await asyncio.sleep(_ANALYTICS_DEBOUNCE_SECONDS)
    metrics = sorted(_pending_analytics_metrics)
    _pending_analytics_metrics.clear()
    if metrics:
        await publish_miniapp_event("analytics_changed", {"metrics": metrics})


# fan out mini app events to local subscribers
async def publish_miniapp_event(event_type: str, payload: dict[str, Any]) -> None:
    public_payload = dict(payload)
    raw_target_user_ids = public_payload.pop("target_user_ids", []) or []
    message = {"type": event_type, **public_payload}
    target_user_ids = {
        int(user_id) for user_id in raw_target_user_ids if user_id is not None
    }
    for user_id, queue in tuple(_subscribers):
        if target_user_ids and user_id not in target_user_ids:
            continue
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # a slow client filled its buffer: drop its oldest message and keep
            # the newest instead of evicting the subscriber outright. Evicting
            # left the client silently connected-but-dead until its 5 min cap;
            # dropping-oldest keeps the stream live and the bounded fallback poll
            # reconciles whatever was shed.
            with suppress(asyncio.QueueEmpty, asyncio.QueueFull):
                queue.get_nowait()
                queue.put_nowait(message)


# notify clients after review deletion
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


# stream mini app events as server-sent events
async def subscribe_miniapp_events(
    user_id: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=20)
    subscriber = (user_id, queue)
    _subscribers.add(subscriber)
    try:
        while True:
            yield await queue.get()
    finally:
        with suppress(KeyError):
            _subscribers.remove(subscriber)
