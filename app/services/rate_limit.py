from __future__ import annotations

import logging

from app.db.redis import get_redis

logger = logging.getLogger(__name__)


async def check_bot_rate_limit(
    user_id: int, action: str, limit: int, window: int
) -> bool:
    """Returns True if allowed, False if limit exceeded."""
    try:
        r = get_redis()
        key = f"rate:bot:{user_id}:{action}"
        pipe = r.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, window, nx=True)
        pipe.ttl(key)
        results = await pipe.execute()
        count: int = results[0]
        if results[2] < 0:
            await r.expire(key, window)
        if count > limit:
            logger.warning(
                "rate_limit_exceeded key=%s limit=%d window=%d", key, limit, window
            )
            return False
        return True
    except Exception:
        # Redis unavailable — allow through
        return True
