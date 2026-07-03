from __future__ import annotations

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.user import User
from app.web.flutter_auth import create_flutter_token
from app.web.schemas import (
    FlutterAuthResponse,
    FlutterLoginRequest,
    FlutterRegisterRequest,
)

router = APIRouter(prefix="/api/flutter/auth", tags=["flutter-auth"])

# generic message so login failures never reveal which field was wrong
_INVALID_CREDENTIALS = "Invalid email or password"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _auth_response(user: User) -> FlutterAuthResponse:
    return FlutterAuthResponse(
        token=create_flutter_token(user),
        user_id=user.id,
        role=user.role,
        first_name=user.first_name,
        is_verified=user.is_verified,
    )


@router.post("/register", response_model=FlutterAuthResponse, status_code=201)
async def register(
    payload: FlutterRegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> FlutterAuthResponse:
    email = _normalize_email(payload.email)

    existing = await session.scalar(
        select(User).where(func.lower(User.email) == email)
    )
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


@router.post("/login", response_model=FlutterAuthResponse)
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
