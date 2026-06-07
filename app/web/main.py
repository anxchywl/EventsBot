from __future__ import annotations

import time
from hashlib import sha256
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
    verify_session_token,
)
from app.config import get_settings
from app.web.routers import (
    events_router,
    favorites_router,
    friends_router,
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
MAX_RATE_LIMIT_KEYS = 20_000

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    from app.web.sync_listener import start_event_cache_invalidation_listener
    app.state.event_cache_listener_task = start_event_cache_invalidation_listener()
    yield
    # shutdown
    task = getattr(app.state, "event_cache_listener_task", None)
    if task:
        task.cancel()


web_app = FastAPI(
    title="Events Bot Mini App",
    lifespan=lifespan,
    docs_url=None,     # Disable Swagger UI in production
    redoc_url=None,    # Disable ReDoc in production
    openapi_url=None,  # Disable OpenAPI schema endpoint
)
web_app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
web_app.include_router(events_router)
web_app.include_router(favorites_router)
web_app.include_router(friends_router)
web_app.include_router(reminders_router)
web_app.include_router(sharing_router)
web_app.include_router(media_router)
web_app.include_router(auth_router)
web_app.include_router(ratings_router)
web_app.include_router(admin_router)


@web_app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Add Global Security Headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "frame-ancestors https://*.telegram.org https://*.telegram.me;"
    
    # Add strong caching headers for static assets
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        
    return response


@web_app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        # Max request body size: 150KB
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 150_000:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body too large"},
            )

        auth_header = request.headers.get("authorization")
        key = request.client.host if request.client else "unknown"
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.removeprefix("Bearer ").strip()
                miniapp_user = verify_session_token(token)
                key = f"user:{miniapp_user.id}"
            except Exception:
                key = f"bad-auth:{sha256(auth_header.encode()).hexdigest()[:16]}"

        now = time.time()
        if len(rate_limits) > MAX_RATE_LIMIT_KEYS:
            _prune_rate_limits(now)

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

        # 6. SSE Connections Rate Limit (Max 15 connections / 1 minute)
        elif request.url.path in {"/api/events/review-updates", "/api/events/updates"}:
            sse_key = f"sse:{key}"
            sse_hits = [ts for ts in rate_limits.get(sse_key, []) if now - ts < 60]
            if len(sse_hits) >= 15:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many streaming connections. Try again later."},
                )
            sse_hits.append(now)
            rate_limits[sse_key] = sse_hits

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


def _prune_rate_limits(now: float) -> None:
    cutoff = now - 900
    stale_keys = [
        key
        for key, hits in rate_limits.items()
        if not hits or max(hits) < cutoff
    ]
    for key in stale_keys:
        rate_limits.pop(key, None)
    if len(rate_limits) <= MAX_RATE_LIMIT_KEYS:
        return
    for key in sorted(rate_limits, key=lambda item_key: max(rate_limits[item_key] or [0]))[
        : len(rate_limits) - MAX_RATE_LIMIT_KEYS
    ]:
        rate_limits.pop(key, None)


@web_app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@web_app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "images" / "default-banner.jpg")


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


@web_app.get("/friends/invite/{token}")
async def friend_invite_page(token: str) -> FileResponse:
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
