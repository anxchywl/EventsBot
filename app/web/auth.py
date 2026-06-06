from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models.user import User


@dataclass
class MiniAppUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_bot: bool = False


def verify_init_data(init_data: str) -> MiniAppUser:
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Telegram hash")

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

    auth_date = int(values.get("auth_date", "0") or "0")
    if auth_date <= 0 or time.time() - auth_date > get_settings().miniapp_session_ttl_seconds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Expired Telegram initData")

    raw_user = values.get("user")
    if not raw_user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Telegram user")

    user_data = json.loads(raw_user)
    return MiniAppUser(
        id=int(user_data["id"]),
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        language_code=user_data.get("language_code"),
        is_bot=bool(user_data.get("is_bot", False)),
    )


def create_session_token(user: MiniAppUser) -> str:
    settings = get_settings()
    expires_at = int(time.time()) + settings.miniapp_session_ttl_seconds
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
        "is_bot": user.is_bot,
        "exp": expires_at,
    }
    header_part = _b64(json.dumps(header, separators=(",", ":")).encode())
    payload_part = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signed_value = f"{header_part}.{payload_part}".encode()
    signature = _b64(_sign(signed_value))
    return f"{header_part}.{payload_part}.{signature}"


def verify_session_token(token: str) -> MiniAppUser:
    try:
        header_part, payload_part, signature = token.split(".", 2)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc

    expected_signature = _b64(_sign(f"{header_part}.{payload_part}".encode()))
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")

    header = json.loads(base64.urlsafe_b64decode(_pad_b64(header_part)))
    if header.get("alg") != "HS256":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")

    payload = json.loads(base64.urlsafe_b64decode(_pad_b64(payload_part)))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Expired session")

    return MiniAppUser(
        id=int(payload["telegram_id"]),
        username=payload.get("username"),
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        language_code=payload.get("language_code"),
        is_bot=bool(payload.get("is_bot", False)),
    )


async def require_miniapp_user(
    authorization: str | None = Header(default=None),
) -> MiniAppUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing session")
    return verify_session_token(authorization.removeprefix("Bearer ").strip())


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


async def optional_miniapp_user(
    authorization: str | None = Header(default=None),
) -> MiniAppUser | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return verify_session_token(authorization.removeprefix("Bearer ").strip())
    except HTTPException:
        return None


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

    user.username = miniapp_user.username
    user.first_name = miniapp_user.first_name
    user.last_name = miniapp_user.last_name
    user.language_code = miniapp_user.language_code
    user.is_bot = miniapp_user.is_bot
    user.last_active_at = datetime.now()

    await session.flush()
    return user


def effective_web_role(user: User, telegram_id: int) -> str:
    admin_ids: set[int] = set()
    for admin_id in get_settings().admin_ids:
        try:
            admin_ids.add(abs(int(admin_id)))
        except (TypeError, ValueError):
            continue
    try:
        normalized_telegram_id = abs(int(telegram_id))
    except (TypeError, ValueError):
        normalized_telegram_id = 0
    if normalized_telegram_id in admin_ids or user.role in ("admin", "super_admin"):
        return "admin"
    if user.role == "moderator":
        return "moderator"
    return "user"


def _sign(value: bytes) -> bytes:
    secret = get_settings().bot_token.get_secret_value().encode()
    return hmac.new(secret, value, hashlib.sha256).digest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _pad_b64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode()


async def require_verified_user(
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
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
    # Update last active
    user.last_active_at = datetime.now()
    await session.commit()
    return user

async def require_verified_user_allow_blocked(
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
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
    # Update last active
    user.last_active_at = datetime.now()
    await session.commit()
    return user

async def require_admin_or_moderator(
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await upsert_miniapp_user(session, miniapp_user)
    role = effective_web_role(user, miniapp_user.id)
    if role not in ("admin", "moderator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin or moderator role required.",
        )
    await session.commit()
    return user

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
