from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


# retry telegram calls when flood control asks us to wait
async def call_with_telegram_backoff(
    operation: Callable[[], Awaitable[T]],
    *,
    context: str,
) -> T:
    settings = get_settings()
    max_retries = max(0, settings.telegram_delivery_max_retries)

    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except TelegramRetryAfter as exc:
            if attempt >= max_retries:
                raise

            retry_after = float(getattr(exc, "retry_after", 1) or 1)
            # jitter the wait so many messages that hit flood control together do
            # not all retry on the same instant and re-trigger flood control
            wait_seconds = retry_after + 0.5 + secrets.randbelow(500) / 1000.0
            logger.warning(
                "telegram flood control for %s; retrying in %.1fs",
                context,
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)

    raise RuntimeError("unreachable telegram retry state")


# avoid sending bursts of telegram messages
async def pause_between_telegram_deliveries() -> None:
    delay = max(0.0, get_settings().telegram_delivery_delay_seconds)
    if delay:
        await asyncio.sleep(delay)


# detect telegram errors that mean delivery should stop
def is_bot_removed_error(error: Exception) -> bool:
    if isinstance(error, TelegramForbiddenError):
        return True

    message = str(error).lower()
    return (
        "bot was kicked" in message
        or "bot is not a member" in message
        or "forbidden: bot" in message
    )
