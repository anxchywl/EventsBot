from __future__ import annotations

from io import BytesIO

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.services.events import get_available_event_by_public_token


router = APIRouter(prefix="/api/events", tags=["miniapp-media"])


@router.get("/{public_token}/cover")
async def event_cover(
    public_token: str,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    event = await get_available_event_by_public_token(session, public_token)
    if not event or not event.poster_file_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cover not found")

    bot = Bot(token=get_settings().bot_token.get_secret_value())
    try:
        file = await bot.get_file(event.poster_file_id)
        if not file.file_path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Cover not found")
        buffer = BytesIO()
        await bot.download_file(file.file_path, destination=buffer)
        buffer.seek(0)
    finally:
        await bot.session.close()

    return StreamingResponse(
        buffer,
        media_type=_image_media_type(file.file_path),
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _image_media_type(file_path: str) -> str:
    clean = file_path.lower()
    if clean.endswith(".png"):
        return "image/png"
    if clean.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"
