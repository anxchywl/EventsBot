from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.db.redis import get_redis

logger = logging.getLogger(__name__)


async def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
    detail: str = "Too many requests.",
) -> None:
    r = get_redis()
    try:
        pipe = r.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        pipe.ttl(key)
        results = await pipe.execute()
    except Exception as exc:
        logger.warning("rate limit storage unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable.",
        ) from exc
    count: int = results[0]
    if results[2] < 0:
        await r.expire(key, window_seconds)
    if count > limit:
        logger.warning(
            "rate_limit_exceeded key=%s limit=%d window=%d", key, limit, window_seconds
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"detail": detail, "retry_after": window_seconds},
            headers={"Retry-After": str(window_seconds)},
        )
