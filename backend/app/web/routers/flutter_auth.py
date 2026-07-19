from __future__ import annotations

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models.user import User
from app.web.flutter_auth import create_flutter_token, require_flutter_user
from app.web.schemas import (
    FlutterAuthResponse,
    FlutterLoginRequest,
    FlutterRegisterRequest,
    FlutterSessionResponse,
)

router = APIRouter(prefix="/api/flutter/auth", tags=["flutter-auth"])

# generic message so login failures never reveal which field was wrong
_INVALID_CREDENTIALS = "Invalid email or password"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def require_native_flutter_auth() -> None:
    if not get_settings().flutter_native_auth_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def _auth_response(user: User) -> FlutterAuthResponse:
    role = "admin" if user.role == "admin" else "user"
    return FlutterAuthResponse(
        token=create_flutter_token(user),
        user_id=user.id,
        role=role,
        first_name=user.first_name,
        is_verified=user.is_verified,
    )


def _session_response(user: User) -> FlutterSessionResponse:
    return FlutterSessionResponse(
        user_id=user.id,
        role="admin" if user.role == "admin" else "user",
        first_name=user.first_name,
        is_verified=user.is_verified,
    )


@router.get("/session", response_model=FlutterSessionResponse)
async def session_profile(
    user: User = Depends(require_flutter_user),
) -> FlutterSessionResponse:
    return _session_response(user)


@router.post(
    "/register",
    response_model=FlutterAuthResponse,
    status_code=201,
    dependencies=[Depends(require_native_flutter_auth)],
)
async def register(
    payload: FlutterRegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> FlutterAuthResponse:
    email = _normalize_email(payload.email)

    existing = await session.scalar(select(User).where(func.lower(User.email) == email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    password_hash = bcrypt.hashpw(
        payload.password.encode(), bcrypt.gensalt(rounds=12)
    ).decode()

    # telegram_id is a required unique column, so seed a placeholder then flip it
    # to the negative primary key to keep flutter-only accounts unique
    user = User(
        email=email,
        password_hash=password_hash,
        first_name=payload.first_name,
        role="user",
        is_verified=False,
        telegram_id=0,
    )
    session.add(user)
    await session.flush()
    user.telegram_id = -user.id
    await session.flush()
    await session.commit()

    return _auth_response(user)


@router.post(
    "/login",
    response_model=FlutterAuthResponse,
    dependencies=[Depends(require_native_flutter_auth)],
)
async def login(
    payload: FlutterLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> FlutterAuthResponse:
    email = _normalize_email(payload.email)

    user = await session.scalar(
        select(User).where(func.lower(User.email) == email).order_by(User.id)
    )
    if user is None or not user.password_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INVALID_CREDENTIALS)

    if not bcrypt.checkpw(payload.password.encode(), user.password_hash.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INVALID_CREDENTIALS)

    if user.is_blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account suspended")

    return _auth_response(user)
