from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.services.events import get_available_event_by_public_token
from app.web.auth import MiniAppUser, require_current_miniapp_user
from app.web.cache import TTLCache
from app.web.routers.events import validate_public_token


router = APIRouter(prefix="/api/events", tags=["miniapp-media"])
cover_cache = TTLCache(ttl_seconds=60 * 60 * 24, max_items=256)
avatar_cache = TTLCache(ttl_seconds=60 * 60 * 6, max_items=1024)

import time

_MEDIA_RATE_LIMITS: dict[str, list[float]] = {}

# limit telegram media proxy requests
def _check_rate_limit(request: Request, limit: int, window_seconds: int) -> None:
    now = time.time()
    cutoff = now - window_seconds
    host = request.client.host if request.client else "unknown"
    key = f"media:{host}"
    hits = [ts for ts in _MEDIA_RATE_LIMITS.get(key, []) if ts > cutoff]

    # prevent memory leaks by pruning stale keys when dict grows large
    if len(_MEDIA_RATE_LIMITS) > 10000:
        for k in list(_MEDIA_RATE_LIMITS.keys()):
            _MEDIA_RATE_LIMITS[k] = [ts for ts in _MEDIA_RATE_LIMITS[k] if ts > cutoff]
            if not _MEDIA_RATE_LIMITS[k]:
                del _MEDIA_RATE_LIMITS[k]

    if len(hits) >= limit:
        _MEDIA_RATE_LIMITS[key] = hits
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try again later.")
    hits.append(now)
    _MEDIA_RATE_LIMITS[key] = hits
@dataclass(frozen=True)
class CachedMedia:
    content: bytes
    media_type: str
    file_path: str


# serve cached event cover images from telegram
@router.get("/{public_token}/cover")
async def event_cover(
    public_token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    _check_rate_limit(request, limit=60, window_seconds=60)
    public_token = validate_public_token(public_token)
    event = await get_available_event_by_public_token(session, public_token)
    if not event or not event.poster_file_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cover not found")

    cache_key = f"cover:{event.poster_file_id}"
    cached = cover_cache.get(cache_key)
    if cached is None:
        cached = await _download_telegram_file(event.poster_file_id, "Cover")
        cover_cache.set(cache_key, cached)

    return _media_response(cached, max_age=60 * 60 * 24, immutable=True)


# cache telegram media with size and type checks
async def _download_telegram_file(file_id: str, label: str) -> CachedMedia:
    bot = Bot(token=get_settings().bot_token.get_secret_value())
    try:
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
            
        # cap media size before storing bytes in memory
        if file.file_size and file.file_size > 5_000_000:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"{label} is too large to cache")
            
        buffer = BytesIO()
        await bot.download_file(file.file_path, destination=buffer)
        return CachedMedia(
            content=buffer.getvalue(),
            media_type=_image_media_type(file.file_path),
            file_path=file.file_path,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} fetch failed: {exc}")
    finally:
        await bot.session.close()


# infer image response type from telegram path
def _image_media_type(file_path: str) -> str:
    clean = file_path.lower()
    if clean.endswith(".png"):
        return "image/png"
    if clean.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


# return cached bytes with browser cache headers
def _media_response(media: CachedMedia, *, max_age: int, immutable: bool = False) -> StreamingResponse:
    cache_control = f"public, max-age={max_age}"
    if immutable:
        cache_control = f"{cache_control}, immutable"
    return StreamingResponse(
        BytesIO(media.content),
        media_type=media.media_type,
        headers={
            "Cache-Control": cache_control,
            "Content-Length": str(len(media.content)),
            "X-Content-Type-Options": "nosniff",
        },
    )


# serve cached user avatar images from telegram
@router.get("/avatar/{telegram_id}")
async def user_avatar(
    telegram_id: int,
    request: Request,
    v: str = Query("", max_length=128),
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
) -> StreamingResponse:
    _check_rate_limit(request, limit=60, window_seconds=60)
    if telegram_id <= 0 or telegram_id != miniapp_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avatar not found")

    cache_key = f"avatar:{telegram_id}:{v}"
    cached = avatar_cache.get(cache_key)
    if cached is not None:
        return _media_response(cached, max_age=60 * 60)

    bot = Bot(token=get_settings().bot_token.get_secret_value())
    try:
        photos = await bot.get_user_profile_photos(user_id=telegram_id, limit=1)
        if not photos or photos.total_count == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile photos found")
        
        # use the smallest telegram avatar for fast mini app loading
        sizes = photos.photos[0]
        photo = sizes[0]
        file = await bot.get_file(photo.file_id)
        if not file.file_path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File path not found")
        
        buffer = BytesIO()
        await bot.download_file(file.file_path, destination=buffer)
        cached = CachedMedia(
            content=buffer.getvalue(),
            media_type=_image_media_type(file.file_path),
            file_path=file.file_path,
        )
        avatar_cache.set(cache_key, cached)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avatar fetch failed") from exc
    finally:
        await bot.session.close()

    return _media_response(cached, max_age=60 * 60)
