from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models.user import User

FLUTTER_JWT_ALGORITHM = "HS256"
FLUTTER_JWT_ISSUER = "nu-events-flutter"
FLUTTER_JWT_AUDIENCE = "nu-events-flutter"
FLUTTER_TOKEN_TTL = timedelta(days=30)


# flutter tokens sign with the independent session secret, never the bot token
def _flutter_jwt_secret() -> str:
    settings = get_settings()
    if settings.session_secret is None:
        raise RuntimeError(
            "SESSION_SECRET must be set — do not leave flutter token signing unkeyed"
        )
    return settings.session_secret.get_secret_value()


# sign a long-lived flutter session token for one user
def create_flutter_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    role = "admin" if user.role == "admin" else "user"
    payload = {
        "iss": FLUTTER_JWT_ISSUER,
        "aud": FLUTTER_JWT_AUDIENCE,
        "sub": str(user.id),
        "role": role,
        "iat": now,
        "exp": now + FLUTTER_TOKEN_TTL,
    }
    return jwt.encode(payload, _flutter_jwt_secret(), algorithm=FLUTTER_JWT_ALGORITHM)


# decode and validate a flutter token, returning the full payload
def decode_flutter_token(token: str) -> dict:
    return jwt.decode(
        token,
        _flutter_jwt_secret(),
        algorithms=[FLUTTER_JWT_ALGORITHM],
        issuer=FLUTTER_JWT_ISSUER,
        audience=FLUTTER_JWT_AUDIENCE,
    )


# resolve the flutter user from a bearer token
async def require_flutter_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing authentication")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_flutter_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    if user.is_blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account suspended")
    return user


# restrict endpoints to admin flutter users
async def require_flutter_admin(
    user: User = Depends(require_flutter_user),
) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return user
