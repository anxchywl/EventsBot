from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from binascii import Error as BinasciiError
from dataclasses import dataclass
from datetime import datetime, UTC
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Request, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models.user import User


# hold verified telegram mini app identity data
@dataclass
class MiniAppUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_bot: bool = False
    photo_url: str | None = None


SESSION_ISSUER = "nu-events-miniapp"
SESSION_AUDIENCE = "nu-events-web"
SESSION_TOKEN_TYPE = "miniapp-session"
MAX_INIT_DATA_FUTURE_SKEW_SECONDS = 60
MAX_INIT_DATA_LENGTH = 8192


# validate telegram init data before trusting user identity
def verify_init_data(init_data: str) -> MiniAppUser:
    if not init_data or len(init_data) > MAX_INIT_DATA_LENGTH:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram initData")

    values: dict[str, str] = {}
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid Telegram initData"
        ) from exc
    for key, value in pairs:
        if key in values:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid Telegram initData"
            )
        values[key] = value

    received_hash = values.pop("hash", None)
    if not received_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Telegram hash")
    if not _is_hex_sha256(received_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram initData")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    bot_token = get_settings().bot_token.get_secret_value()
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram initData")

    try:
        auth_date = int(values.get("auth_date", "0") or "0")
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid Telegram initData"
        ) from exc

    now = int(time.time())
    if (
        auth_date <= 0
        or auth_date > now + MAX_INIT_DATA_FUTURE_SKEW_SECONDS
        or now - auth_date > get_settings().miniapp_session_ttl_seconds
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Expired Telegram initData")

    raw_user = values.get("user")
    if not raw_user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Telegram user")

    try:
        user_data = json.loads(raw_user)
        telegram_id = int(user_data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid Telegram user"
        ) from exc

    if telegram_id <= 0 or bool(user_data.get("is_bot", False)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram user")

    return MiniAppUser(
        id=telegram_id,
        username=_optional_str(user_data.get("username"), max_len=255),
        first_name=_optional_str(user_data.get("first_name"), max_len=255),
        last_name=_optional_str(user_data.get("last_name"), max_len=255),
        language_code=_optional_str(user_data.get("language_code"), max_len=16),
        is_bot=False,
        photo_url=_optional_str(user_data.get("photo_url"), max_len=1024),
    )


# return the real client IP, trusting X-Forwarded-For only from configured proxy IPs
def get_real_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    trusted = set(get_settings().trusted_proxy_ips)
    if direct_ip in trusted:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip() or direct_ip
    return direct_ip


# sign mini app session data for authenticated api calls
def create_session_token(user: MiniAppUser) -> str:
    settings = get_settings()
    issued_at = int(time.time())
    expires_at = issued_at + settings.miniapp_session_ttl_seconds
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": SESSION_ISSUER,
        "aud": SESSION_AUDIENCE,
        "typ": SESSION_TOKEN_TYPE,
        "sub": str(user.id),
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
        "is_bot": user.is_bot,
        "photo_url": user.photo_url,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
    }
    header_part = _b64(json.dumps(header, separators=(",", ":")).encode())
    payload_part = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signed_value = f"{header_part}.{payload_part}".encode()
    signature = _b64(_sign(signed_value))
    return f"{header_part}.{payload_part}.{signature}"


# verify signed mini app session data
def verify_session_token(token: str) -> MiniAppUser:
    if not token or len(token) > 4096:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    try:
        header_part, payload_part, signature = token.split(".", 2)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc

    expected_signature = _b64(_sign(f"{header_part}.{payload_part}".encode()))
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")

    try:
        header = json.loads(base64.urlsafe_b64decode(_pad_b64(header_part)))
    except (BinasciiError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc
    if header.get("alg") != "HS256":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")

    try:
        payload = json.loads(base64.urlsafe_b64decode(_pad_b64(payload_part)))
        telegram_id = int(payload["telegram_id"])
        exp = int(payload.get("exp", 0))
        nbf = int(payload.get("nbf", 0) or 0)
    except (
        KeyError,
        TypeError,
        ValueError,
        BinasciiError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc

    now = int(time.time())
    if (
        payload.get("iss") != SESSION_ISSUER
        or payload.get("aud") != SESSION_AUDIENCE
        or payload.get("typ") != SESSION_TOKEN_TYPE
        or payload.get("sub") != str(telegram_id)
        or telegram_id <= 0
        or bool(payload.get("is_bot", False))
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    if nbf and nbf > now + MAX_INIT_DATA_FUTURE_SKEW_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    if exp < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Expired session")

    return MiniAppUser(
        id=telegram_id,
        username=_optional_str(payload.get("username"), max_len=255),
        first_name=_optional_str(payload.get("first_name"), max_len=255),
        last_name=_optional_str(payload.get("last_name"), max_len=255),
        language_code=_optional_str(payload.get("language_code"), max_len=16),
        is_bot=False,
        photo_url=_optional_str(payload.get("photo_url"), max_len=1024),
    )


# require a valid mini app session
async def require_miniapp_user(
    authorization: str | None = Header(default=None),
) -> MiniAppUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing session")
    return verify_session_token(authorization.removeprefix("Bearer ").strip())


# require session and matching fresh telegram init data
async def require_current_miniapp_user(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(
        default=None,
        alias="X-Telegram-Init-Data",
    ),
) -> MiniAppUser:
    session_user = await require_miniapp_user(authorization)
    if not x_telegram_init_data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Telegram initData")

    current_user = verify_init_data(x_telegram_init_data)
    if current_user.id != session_user.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telegram account changed")

    return session_user


# read mini app session when available
async def optional_miniapp_user(
    authorization: str | None = Header(default=None),
) -> MiniAppUser | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return verify_session_token(authorization.removeprefix("Bearer ").strip())
    except HTTPException:
        return None


# accept session only when fresh telegram init data matches
async def optional_current_miniapp_user(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(
        default=None,
        alias="X-Telegram-Init-Data",
    ),
) -> MiniAppUser | None:
    if not x_telegram_init_data:
        return None
    try:
        if authorization:
            return await require_current_miniapp_user(
                authorization=authorization,
                x_telegram_init_data=x_telegram_init_data,
            )
        return verify_init_data(x_telegram_init_data)
    except HTTPException:
        return None


# sync telegram identity into the local user record
async def upsert_miniapp_user(session: AsyncSession, miniapp_user: MiniAppUser) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == miniapp_user.id),
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=miniapp_user.id)
        session.add(user)

    from app.config import get_settings

    settings = get_settings()
    if miniapp_user.id in settings.admin_ids:
        user.role = "admin"
    elif user.role not in {"user", "admin"}:
        user.role = "user"

    user.username = miniapp_user.username
    user.first_name = miniapp_user.first_name
    user.last_name = miniapp_user.last_name
    user.language_code = miniapp_user.language_code
    user.is_bot = miniapp_user.is_bot
    user.last_active_at = datetime.now(UTC)

    if miniapp_user.photo_url:
        user.photo_url = miniapp_user.photo_url
        user.photo_updated_at = datetime.now(UTC)

    await session.flush()
    return user


# derive web permissions from admin settings and stored role
def effective_web_role(user: User, telegram_id: int) -> str:
    admin_ids: set[int] = set()
    for admin_id in get_settings().admin_ids:
        try:
            admin_ids.add(int(admin_id))
        except (TypeError, ValueError):
            continue
    try:
        # negative telegram_id signals a de-linked account — must not match positive admin ids
        normalized_telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        normalized_telegram_id = 0
    if normalized_telegram_id in admin_ids or user.role == "admin":
        return "admin"
    return "user"


# sign session payloads with hmac
def _sign(value: bytes) -> bytes:
    return hmac.new(_session_signing_key(), value, hashlib.sha256).digest()


# encode compact url-safe token parts
def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


# restore stripped base64 padding before decode
def _pad_b64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode()


# session tokens must be signed with an independent secret, not the bot token
def _session_signing_key() -> bytes:
    settings = get_settings()
    if settings.session_secret is None:
        raise RuntimeError(
            "SESSION_SECRET must be set — do not leave session signing unkeyed"
        )
    return settings.session_secret.get_secret_value().encode()


# detect legacy sha256-style bot token secrets
def _is_hex_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


# normalize optional telegram string fields
def _optional_str(value: object, *, max_len: int) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    return value[:max_len]


# require verified user
async def require_verified_user(
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await upsert_miniapp_user(session, miniapp_user)
    from app.config import get_settings

    settings = get_settings()
    is_admin = miniapp_user.id in settings.admin_ids
    if user.is_blocked and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been blocked.",
        )
    if not user.is_verified and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nazarbayev University email verification required",
        )
    # keep verified-user activity fresh for admin views
    user.last_active_at = datetime.now(UTC)
    await session.commit()
    return user


# allow blocked users only where logout/history still need access
async def require_verified_user_allow_blocked(
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await upsert_miniapp_user(session, miniapp_user)
    from app.config import get_settings

    settings = get_settings()
    is_admin = miniapp_user.id in settings.admin_ids
    if not user.is_verified and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nazarbayev University email verification required",
        )
    # keep verified-user activity fresh for admin views
    user.last_active_at = datetime.now(UTC)
    await session.commit()
    return user


# guard admin endpoints
async def require_admin(
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await upsert_miniapp_user(session, miniapp_user)
    if effective_web_role(user, miniapp_user.id) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin role required.",
        )
    await session.commit()
    return user
