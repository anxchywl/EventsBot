from __future__ import annotations

import time
from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.db.session import get_session
from app.web.auth import (
    create_session_token,
    effective_web_role,
    upsert_miniapp_user,
    verify_init_data,
)
from app.web.routers import (
    events_router,
    favorites_router,
    media_router,
    reminders_router,
    sharing_router,
    auth_router,
    ratings_router,
    admin_router,
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
web_app.include_router(auth_router)
web_app.include_router(ratings_router)
web_app.include_router(admin_router)


@web_app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        key = request.headers.get("authorization") or request.client.host
        now = time.time()

        # 1. Registration Rate Limit (Max 5 attempts / 15 mins)
        if request.url.path == "/api/auth/register":
            reg_key = f"reg:{key}"
            reg_hits = [ts for ts in rate_limits.get(reg_key, []) if now - ts < 900]
            if len(reg_hits) >= 5:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many registration attempts. Please try again in 15 minutes."},
                )
            reg_hits.append(now)
            rate_limits[reg_key] = reg_hits

        # 2. Login Rate Limit (Max 5 attempts / 15 mins)
        elif request.url.path == "/api/auth/login":
            login_key = f"login:{key}"
            login_hits = [ts for ts in rate_limits.get(login_key, []) if now - ts < 900]
            if len(login_hits) >= 5:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many login attempts. Please try again in 15 minutes."},
                )
            login_hits.append(now)
            rate_limits[login_key] = login_hits

        # 3. Code Resend Rate Limit (Max 3 attempts / 5 mins)
        elif request.url.path == "/api/auth/resend":
            resend_key = f"resend:{key}"
            resend_hits = [ts for ts in rate_limits.get(resend_key, []) if now - ts < 300]
            if len(resend_hits) >= 3:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many code resend requests. Please try again in 5 minutes."},
                )
            resend_hits.append(now)
            rate_limits[resend_key] = resend_hits

        # 4. Verification Rate Limit (Max 10 attempts / 5 mins)
        elif request.url.path == "/api/auth/verify":
            verify_key = f"verify:{key}"
            verify_hits = [ts for ts in rate_limits.get(verify_key, []) if now - ts < 300]
            if len(verify_hits) >= 10:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many verification attempts. Please try again in 5 minutes."},
                )
            verify_hits.append(now)
            rate_limits[verify_key] = verify_hits

        # 5. Password Reset Rate Limit (Max 10 attempts / 15 mins)
        elif request.url.path.startswith("/api/auth/forgot-password/"):
            reset_key = f"reset:{key}"
            reset_hits = [ts for ts in rate_limits.get(reset_key, []) if now - ts < 900]
            if len(reset_hits) >= 10:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many attempts. Try again later"},
                )
            reset_hits.append(now)
            rate_limits[reset_key] = reset_hits

        # General API rate limiting fallback
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
            "email": user.email,
            "nickname": user.nickname,
            "is_verified": user.is_verified,
            "role": effective_web_role(user, miniapp_user.id),
            "is_blocked": user.is_blocked,
            "blocked_reason": user.blocked_reason,
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
