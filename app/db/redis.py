from __future__ import annotations

import redis.asyncio as aioredis

_client: aioredis.Redis | None = None
_media_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        from app.config import get_settings
        _client = aioredis.from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# separate client with decode_responses=False to store raw image bytes
def get_media_redis() -> aioredis.Redis:
    global _media_client
    if _media_client is None:
        from app.config import get_settings
        _media_client = aioredis.from_url(
            get_settings().redis_url,
            decode_responses=False,
        )
    return _media_client


async def close_media_redis() -> None:
    global _media_client
    if _media_client is not None:
        await _media_client.aclose()
        _media_client = None
