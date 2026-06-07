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

# open and close shared web resources around app lifetime
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.web.sync_listener import start_event_cache_invalidation_listener
    app.state.event_cache_listener_task = start_event_cache_invalidation_listener()
    yield
    task = getattr(app.state, "event_cache_listener_task", None)
    if task:
        task.cancel()


web_app = FastAPI(
    title="Events Bot Mini App",
    lifespan=lifespan,
    docs_url=None,     # disable swagger ui in production
    redoc_url=None,    # disable redoc in production
    openapi_url=None,  # disable openapi schema endpoint
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


# set browser security headers for the mini app
@web_app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # restrict framing to telegram clients
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "frame-ancestors https://*.telegram.org https://*.telegram.me;"
    
    # cache static assets aggressively after versioned urls
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        
    return response


# protect auth and realtime endpoints from burst traffic
@web_app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        # reject oversized auth and review payloads early
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

        # rate limit registration attempts per email and ip
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

        # rate limit login attempts per email and ip
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

        # rate limit verification resend attempts
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

        # rate limit verification guesses
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

        # rate limit reset flow attempts by email and ip
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

        # rate limit realtime connection churn
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

        if request.url.path != "/api/auth/session":
            # protect remaining api routes from bursts
            hits = [ts for ts in rate_limits.get(key, []) if now - ts < 60]
            if key.startswith("user:"):
                limit = 180 if request.method not in {"GET", "HEAD", "OPTIONS"} else 600
            else:
                limit = 45 if request.method not in {"GET", "HEAD", "OPTIONS"} else 120
            if len(hits) >= limit:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests"},
                )
            hits.append(now)
            rate_limits[key] = hits
    return await call_next(request)


# drop old rate limit buckets before they grow unbounded
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


# expose a minimal health probe
@web_app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# avoid noisy favicon 404s
@web_app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "images" / "default-banner.jpg")


# exchange telegram init data for a signed session
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


# serve the mini app shell
@web_app.get("/")
async def index() -> FileResponse:
    return _index_response()


# serve the app shell for event deep links
@web_app.get("/events/{public_token}")
async def event_page(public_token: str) -> FileResponse:
    return _index_response()


# serve the app shell for friend invite links
@web_app.get("/friends/invite/{token}")
async def friend_invite_page(token: str) -> FileResponse:
    return _index_response()


# disable caching for the html app shell
def _index_response() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
