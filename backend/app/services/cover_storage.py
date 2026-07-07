from __future__ import annotations

import asyncio
import io
import logging
import secrets

from app.config import get_settings
from app.db.redis import get_media_redis, get_redis
from app.services.image_processing import _detect_image_format, process_image
from app.web.telegram import get_web_bot

logger = logging.getLogger(__name__)

# archived source resolution before serving cache resize
_STORAGE_MAX_PX = 1280

_STAGING_PREFIX = "cover:staging:"
_STAGING_BYTES_PREFIX = "cover:staging:bytes:"

# declared types must agree with magic bytes
_FORMAT_TO_MIME = {
    "jpeg": frozenset({"image/jpeg", "image/jpg", "image/pjpeg"}),
    "png": frozenset({"image/png"}),
    "webp": frozenset({"image/webp"}),
    "gif": frozenset({"image/gif"}),
}
_FORMAT_TO_EXT = {
    "jpeg": frozenset({".jpg", ".jpeg"}),
    "png": frozenset({".png"}),
    "webp": frozenset({".webp"}),
    "gif": frozenset({".gif"}),
}
_ALLOWED_MIME = frozenset().union(*_FORMAT_TO_MIME.values())
_ALLOWED_EXT = frozenset().union(*_FORMAT_TO_EXT.values())


class CoverUploadError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _extension(filename: str | None) -> str:
    # client filenames are never stored
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()


def validate_cover_bytes(
    raw: bytes, filename: str | None, content_type: str | None
) -> bytes:
    settings = get_settings()

    if not raw:
        raise CoverUploadError(400, "The selected file is empty.")
    if len(raw) > settings.media_max_upload_bytes:
        raise CoverUploadError(413, "Image is larger than the 5 MB limit.")

    ext = _extension(filename)
    if ext not in _ALLOWED_EXT:
        raise CoverUploadError(415, "Only JPEG, PNG, WebP or GIF images are accepted.")

    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if ctype not in _ALLOWED_MIME:
        raise CoverUploadError(415, "Unsupported image content type.")

    detected = _detect_image_format(raw)
    if detected is None:
        raise CoverUploadError(415, "The file is not a recognised image.")

    # reject type spoofing before pillow parses bytes
    if ctype not in _FORMAT_TO_MIME[detected] or ext not in _FORMAT_TO_EXT[detected]:
        raise CoverUploadError(415, "File type does not match its contents.")

    try:
        # re-encoding drops exif and embedded payloads
        return process_image(
            raw,
            max_px=_STORAGE_MAX_PX,
            max_size_bytes=settings.media_max_upload_bytes,
            output_format="JPEG",
        )
    except ValueError as exc:
        if "pixel" in str(exc).lower():
            raise CoverUploadError(413, "Image dimensions are too large.") from exc
        raise CoverUploadError(422, "The image is corrupt or unreadable.") from exc


async def store_cover(webp_or_jpeg: bytes) -> str:
    from aiogram.types import BufferedInputFile

    settings = get_settings()
    if settings.media_storage_chat_id is None:
        raise CoverUploadError(503, "Cover uploads are not configured.")

    try:
        message = await get_web_bot().send_photo(
            chat_id=settings.media_storage_chat_id,
            photo=BufferedInputFile(webp_or_jpeg, filename="cover.jpg"),
        )
    except Exception as exc:
        logger.warning("cover storage send failed: %s", exc)
        raise CoverUploadError(502, "Could not store the cover. Please retry.") from exc

    if not message.photo:
        raise CoverUploadError(502, "Cover storage returned no photo.")
    return message.photo[-1].file_id


async def revalidate_stored_cover(file_id: str) -> bool:
    # verify telegram hosts a retrievable image before persisting the id
    settings = get_settings()
    try:
        bot = get_web_bot()
        file = await bot.get_file(file_id)
        if not file.file_path:
            return False
        if file.file_size and file.file_size > settings.media_max_upload_bytes:
            return False
        buffer = io.BytesIO()
        await bot.download_file(file.file_path, destination=buffer)
        await asyncio.to_thread(
            process_image,
            buffer.getvalue(),
            _STORAGE_MAX_PX,
            settings.media_max_upload_bytes,
        )
        return True
    except Exception:
        return False


async def stage_cover_bytes(clean: bytes, user_id: int) -> str:
    # delay telegram storage until submit
    settings = get_settings()
    token = secrets.token_urlsafe(24)
    ttl = settings.media_cover_staging_ttl
    await get_redis().set(f"{_STAGING_PREFIX}{token}", str(user_id), ex=ttl)
    await get_media_redis().set(f"{_STAGING_BYTES_PREFIX}{token}", clean, ex=ttl)
    return token


async def consume_and_store_cover(token: str, user_id: int) -> str | None:
    # foreign tokens must not bind images to another user's event
    if not token:
        return None
    meta_key = f"{_STAGING_PREFIX}{token}"
    bytes_key = f"{_STAGING_BYTES_PREFIX}{token}"
    try:
        owner = await get_redis().get(meta_key)
    except Exception:
        return None
    if owner is None or owner != str(user_id):
        return None
    try:
        data = await get_media_redis().get(bytes_key)
    except Exception:
        data = None
    # prevent replaying the same upload
    try:
        await get_redis().delete(meta_key)
        await get_media_redis().delete(bytes_key)
    except Exception:
        pass
    if not data:
        return None
    file_id = await store_cover(data)
    if not await revalidate_stored_cover(file_id):
        raise CoverUploadError(502, "Cover could not be verified. Please retry.")
    return file_id


async def bust_cover_cache(file_id: str) -> None:
    try:
        await get_media_redis().delete(f"media:cover:{file_id}:cover")
    except Exception:
        pass
