from __future__ import annotations

import time
from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.db.session import get_session
from app.web.auth import create_session_token, upsert_miniapp_user, verify_init_data
from app.web.routers import (
    events_router,
    favorites_router,
    media_router,
    reminders_router,
    sharing_router,
)
from app.web.schemas import AuthRequest, AuthResponse


STATIC_DIR = Path(__file__).parent / "static"
rate_limits: dict[str, list[float]] = {}

web_app = FastAPI(title="Events Bot Mini App")
web_app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
web_app.include_router(events_router)
web_app.include_router(favorites_router)
web_app.include_router(reminders_router)
web_app.include_router(sharing_router)
web_app.include_router(media_router)


@web_app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        key = request.headers.get("authorization") or request.client.host
        now = time.time()
        hits = [ts for ts in rate_limits.get(key, []) if now - ts < 60]
        limit = 45 if request.method not in {"GET", "HEAD", "OPTIONS"} else 120
        if len(hits) >= limit:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests"},
            )
        hits.append(now)
        rate_limits[key] = hits
    return await call_next(request)


@web_app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@web_app.post("/api/auth/session", response_model=AuthResponse)
async def create_session(
    payload: AuthRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    miniapp_user = verify_init_data(payload.init_data)
    user = await upsert_miniapp_user(session, miniapp_user)
    await session.commit()
    return AuthResponse(
        token=create_session_token(miniapp_user),
        user={
            "id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
    )


@web_app.get("/")
async def index() -> FileResponse:
    return _index_response()


@web_app.get("/events/{public_token}")
async def event_page(public_token: str) -> FileResponse:
    return _index_response()


def _index_response() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
