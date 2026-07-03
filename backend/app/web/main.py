from __future__ import annotations

from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.config import get_settings
from app.db.redis import close_media_redis, close_redis, get_redis
from app.web.telegram import close_web_bot
from app.db.session import get_session
from app.web.auth import (
    create_session_token,
    effective_web_role,
    get_real_ip,
    upsert_miniapp_user,
    verify_init_data,
    verify_session_token,
)
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
    flutter_auth_router,
    flutter_events_router,
)
from app.web.schemas import AuthRequest, AuthResponse


STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "static"


# open and close shared web resources around app lifetime
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.web.sync_listener import start_event_cache_invalidation_listener

    app.state.event_cache_listener_task = start_event_cache_invalidation_listener()
    yield
    task = getattr(app.state, "event_cache_listener_task", None)
    if task:
        task.cancel()
    await close_redis()
    await close_media_redis()
    await close_web_bot()


# read settings before app construction so docs can be enabled for development
_settings = get_settings()

web_app = FastAPI(
    title="Events Bot Mini App",
    lifespan=lifespan,
    # docs disabled in production, enabled when FLUTTER_DEV_DOCS is set
    docs_url="/documentation" if _settings.flutter_dev_docs else None,
    redoc_url=None,  # disable redoc in production
    openapi_url="/openapi.json" if _settings.flutter_dev_docs else None,
)

_cors_origins = ["https://web.telegram.org", "https://k.snek.sh"]
if _settings.flutter_dev_cors:
    _cors_origins += ["http://localhost:*", "http://10.0.2.2:*"]

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Telegram-Init-Data",
        "X-Language",
        "X-Theme",
    ],
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
web_app.include_router(flutter_auth_router)
web_app.include_router(flutter_events_router)


# set browser security headers for the mini app
@web_app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)

    # restrict framing to telegram clients
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors https://*.telegram.org https://*.telegram.me;"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # cache static assets aggressively after versioned urls
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

    return response


# protect auth and realtime endpoints from burst traffic
@web_app.middleware("http")
async def rate_limit(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # enforce body size limit on actual bytes, not client-supplied Content-Length
    if request.method in {"POST", "PUT", "PATCH"}:
        body = await request.body()
        if len(body) > 150_000:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body too large"},
            )

    auth_header = request.headers.get("authorization")
    key = get_real_ip(request)
    if auth_header and auth_header.startswith("Bearer "):
        try:
            miniapp_user = verify_session_token(
                auth_header.removeprefix("Bearer ").strip()
            )
            key = f"user:{miniapp_user.id}"
        except Exception:
            key = f"bad-auth:{sha256(auth_header.encode()).hexdigest()[:16]}"

    try:
        r = get_redis()
        path = request.url.path

        # endpoint-specific limits
        if path == "/api/auth/session":
            await _rl(
                r,
                f"rate:ip:{key}:session",
                30,
                60,
                "Too many session requests. Try again later.",
            )
        elif path == "/api/auth/register":
            await _rl(
                r,
                f"rate:ip:{key}:register",
                5,
                900,
                "Too many registration attempts. Please try again in 15 minutes.",
            )
        elif path == "/api/auth/login":
            await _rl(
                r,
                f"rate:ip:{key}:login",
                5,
                900,
                "Too many login attempts. Please try again in 15 minutes.",
            )
        elif path == "/api/auth/resend":
            await _rl(
                r,
                f"rate:ip:{key}:resend",
                3,
                300,
                "Too many code resend requests. Please try again in 5 minutes.",
            )
        elif path == "/api/auth/verify":
            await _rl(
                r,
                f"rate:ip:{key}:verify",
                10,
                300,
                "Too many verification attempts. Please try again in 5 minutes.",
            )
        elif path.startswith("/api/auth/forgot-password/"):
            await _rl(
                r, f"rate:ip:{key}:fp", 10, 900, "Too many attempts. Try again later."
            )
        elif path == "/api/flutter/auth/login":
            await _rl(
                r,
                f"rate:ip:{key}:flutter-login",
                10,
                900,
                "Too many login attempts. Please try again in 15 minutes.",
            )
        elif path == "/api/flutter/auth/register":
            await _rl(
                r,
                f"rate:ip:{key}:flutter-register",
                5,
                900,
                "Too many registration attempts. Please try again in 15 minutes.",
            )
        elif path in {"/api/events/review-updates", "/api/events/updates"}:
            await _rl(
                r,
                f"rate:ip:{key}:sse",
                15,
                60,
                "Too many streaming connections. Try again later.",
            )

        # global burst guard (skip the session exchange endpoint — it has its own auth)
        if path != "/api/auth/session":
            if key.startswith("user:"):
                burst = 180 if request.method not in {"GET", "HEAD", "OPTIONS"} else 600
            else:
                burst = 45 if request.method not in {"GET", "HEAD", "OPTIONS"} else 120
            await _rl(r, f"rate:global:{key}", burst, 60)

    except HTTPException as exc:
        headers = (
            {"Retry-After": str(exc.headers["Retry-After"])}
            if exc.headers and "Retry-After" in exc.headers
            else {}
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )
    except Exception:
        # Redis unavailable — degrade gracefully rather than blocking all requests
        pass

    return await call_next(request)


async def _rl(
    r, key: str, limit: int, window: int, detail: str = "Too many requests."
) -> None:
    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, window, nx=True)
    pipe.ttl(key)
    results = await pipe.execute()
    if results[2] < 0:
        await r.expire(key, window)
    if results[0] > limit:
        import logging

        logging.getLogger(__name__).warning(
            "rate_limit_exceeded key=%s limit=%d window=%d", key, limit, window
        )
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail,
            headers={"Retry-After": str(window)},
        )


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
