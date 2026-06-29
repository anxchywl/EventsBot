from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.services.event_sync import listen_for_event_sync_notifications
from app.web.routers.events import event_cache

logger = logging.getLogger(__name__)


# listen for postgres sync notifications and clear caches
async def run_event_cache_invalidation_listener() -> None:
    def clear_cache(_payload: str) -> None:
        event_cache.clear()
        logger.info("cleared mini-app event cache after event sync notification")

    await listen_for_event_sync_notifications(get_settings().database_url, clear_cache)


# start cache invalidation listener once per process
def start_event_cache_invalidation_listener() -> asyncio.Task:
    return asyncio.create_task(
        run_event_cache_invalidation_listener(),
        name="event_cache_invalidation_listener",
    )
