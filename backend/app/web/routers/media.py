from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.redis import get_media_redis
from app.db.session import get_session
from app.services.events import get_event_by_public_token
from app.services.image_processing import process_image
from app.web.auth import MiniAppUser, get_real_ip, require_current_miniapp_user
from app.web.limiter import check_rate_limit
from app.web.routers.events import validate_public_token
from app.web.telegram import get_web_bot


router = APIRouter(prefix="/api/events", tags=["miniapp-media"])


class _LimitedBytesIO(BytesIO):
    def __init__(self, max_size_bytes: int) -> None:
        super().__init__()
        self._max_size_bytes = max_size_bytes

    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > self._max_size_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large to cache"
            )
        return super().write(data)


@router.get("/{public_token}/cover")
async def event_cover(
    public_token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    await check_rate_limit(
        f"rate:ip:{get_real_ip(request)}:cover_media",
        60,
        60,
        "Too many media requests. Try again later.",
    )
    public_token = validate_public_token(public_token)
    event = await get_event_by_public_token(session, public_token)
    if not event or not event.poster_file_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cover not found")

    settings = get_settings()
    redis_key = f"media:cover:{event.poster_file_id}:cover"

    try:
        cached = await get_media_redis().get(redis_key)
        if cached is not None:
            return _media_response(
                cached,
                max_age=settings.media_cover_cache_ttl,
                immutable=True,
                public=True,
            )
    except Exception:
        pass

    raw = await _download_raw(
        event.poster_file_id, "Cover", settings.media_max_upload_bytes
    )
    try:
        webp = process_image(
            raw, max_px=800, max_size_bytes=settings.media_max_upload_bytes
        )
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid image")

    try:
        await get_media_redis().set(redis_key, webp, ex=settings.media_cover_cache_ttl)
    except Exception:
        pass

    return _media_response(
        webp, max_age=settings.media_cover_cache_ttl, immutable=True, public=True
    )


@router.get("/avatar/{telegram_id}")
async def user_avatar(
    telegram_id: int,
    request: Request,
    v: str = Query("", max_length=128),
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
) -> StreamingResponse:
    await check_rate_limit(
        f"rate:ip:{get_real_ip(request)}:avatar_media",
        60,
        60,
        "Too many media requests. Try again later.",
    )
    if telegram_id <= 0 or telegram_id != miniapp_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avatar not found")

    settings = get_settings()
    redis_key = f"media:avatar:{telegram_id}:{v}:avatar"

    try:
        cached = await get_media_redis().get(redis_key)
        if cached is not None:
            return _media_response(
                cached, max_age=settings.media_avatar_cache_ttl, public=False
            )
    except Exception:
        pass

    try:
        photos = await get_web_bot().get_user_profile_photos(
            user_id=telegram_id, limit=1
        )
        if not photos or photos.total_count == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile photos found")
        photo = photos.photos[0][0]
        file = await get_web_bot().get_file(photo.file_id)
        if not file.file_path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File path not found")
        if file.file_size and file.file_size > settings.media_max_upload_bytes:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Avatar not found")
        buffer = _LimitedBytesIO(settings.media_max_upload_bytes)
        await get_web_bot().download_file(file.file_path, destination=buffer)
        raw = buffer.getvalue()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avatar fetch failed")

    try:
        webp = process_image(
            raw, max_px=100, max_size_bytes=settings.media_max_upload_bytes
        )
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avatar not found")

    try:
        await get_media_redis().set(redis_key, webp, ex=settings.media_avatar_cache_ttl)
    except Exception:
        pass

    return _media_response(webp, max_age=settings.media_avatar_cache_ttl, public=False)


async def _download_raw(file_id: str, label: str, max_size_bytes: int) -> bytes:
    try:
        bot = get_web_bot()
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
        if file.file_size and file.file_size > max_size_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"{label} is too large to cache",
            )
        buffer = _LimitedBytesIO(max_size_bytes)
        await bot.download_file(file.file_path, destination=buffer)
        return buffer.getvalue()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} fetch failed")


def _media_response(
    data: bytes, *, max_age: int, immutable: bool = False, public: bool = True
) -> StreamingResponse:
    cache_control = f"{'public' if public else 'private'}, max-age={max_age}"
    if immutable:
        cache_control = f"{cache_control}, immutable"
    return StreamingResponse(
        BytesIO(data),
        media_type="image/webp",
        headers={
            "Cache-Control": cache_control,
            "Content-Length": str(len(data)),
            "X-Content-Type-Options": "nosniff",
        },
    )
