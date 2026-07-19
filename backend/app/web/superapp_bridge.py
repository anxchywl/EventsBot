"""University superapp identity bridge.

This is the single seam for migrating the Flutter coordinator app into the
university superapp. It is inert by default: with no `SUPERAPP_*` settings
configured, `try_superapp_user()` returns ``None``. Native Flutter tokens are
accepted separately only in an explicitly enabled debug backend.

When the superapp is ready, set the `SUPERAPP_JWT_*` env vars (see config.py).
Flutter endpoints then accept a superapp-issued JWT without changing endpoint
authorization or trusting identity and role data from the Flutter client.

No assumption is made about the superapp's internals beyond "it can hand the
webview a signed JWT" — the standard OIDC/JWT shape. If the superapp instead
authenticates via a gateway-injected header or mTLS, this module is the only
place that changes: swap `decode_superapp_token()` for a header/cert check and
keep `resolve_or_create_superapp_user()` as-is.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC

import jwt
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

logger = logging.getLogger(__name__)


def superapp_bridge_enabled() -> bool:
    return get_settings().superapp_bridge_enabled


# verify a superapp JWT with the configured key/algorithm/issuer/audience.
# raises jwt.InvalidTokenError on any failure (bad signature, wrong iss/aud,
# expired). Callers treat that as "not a valid superapp token".
def decode_superapp_token(token: str) -> dict:
    settings = get_settings()
    key: str
    if settings.superapp_jwt_public_key:
        key = settings.superapp_jwt_public_key
    elif settings.superapp_jwt_secret is not None:
        key = settings.superapp_jwt_secret.get_secret_value()
    else:  # pragma: no cover - guarded by superapp_bridge_enabled
        raise jwt.InvalidTokenError("superapp bridge is not configured")

    options = {"require": ["exp"]}
    decode_kwargs: dict = {
        "algorithms": [settings.superapp_jwt_algorithm],
        "options": options,
    }
    # only enforce audience when configured; PyJWT rejects tokens that carry an
    # aud when the verifier passes none, so omit the kwarg if unset
    if settings.superapp_jwt_audience:
        decode_kwargs["audience"] = settings.superapp_jwt_audience
    else:
        options["verify_aud"] = False
    if settings.superapp_jwt_issuer:
        decode_kwargs["issuer"] = settings.superapp_jwt_issuer

    return jwt.decode(token, key, **decode_kwargs)


def _extract_subject(claims: dict) -> str | None:
    raw = claims.get(get_settings().superapp_user_id_claim)
    if raw is None:
        return None
    subject = str(raw).strip()
    if not subject or len(subject) > 255:
        return None
    return subject


# never trust an unverified role: default everyone to "user" and only elevate to
# admin when a configured role claim exactly matches the configured admin value.
def _role_from_claims(claims: dict) -> str | None:
    settings = get_settings()
    if not settings.superapp_role_claim or not settings.superapp_admin_role_value:
        return None
    value = claims.get(settings.superapp_role_claim)
    if value is None:
        return None
    return "admin" if str(value) == settings.superapp_admin_role_value else "user"


# map a verified superapp identity to exactly one local User, provisioning a new
# row on first sight. Mirrors upsert_miniapp_user for the Telegram surface.
async def resolve_or_create_superapp_user(
    session: AsyncSession, claims: dict
) -> User | None:
    subject = _extract_subject(claims)
    if subject is None:
        return None

    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(f"superapp-user:{subject}", 0)
            )
        )
    )

    user = await session.scalar(select(User).where(User.superapp_user_id == subject))
    if user is None:
        # telegram_id is a required unique column; seed 0 then flip to the
        # negative primary key, exactly as the legacy Flutter register did, so
        # superapp-only accounts stay unique without colliding with Telegram ids
        user = User(
            superapp_user_id=subject,
            role="user",
            is_verified=True,  # identity is asserted by the superapp itself
            telegram_id=0,
        )
        session.add(user)
        await session.flush()
        user.telegram_id = -user.id

    # keep the mapped role in sync when the superapp asserts one
    claim_role = _role_from_claims(claims)
    if claim_role is not None:
        user.role = claim_role

    # opportunistically refresh display fields when present
    first_name = claims.get("given_name") or claims.get("first_name")
    if isinstance(first_name, str) and first_name.strip():
        user.first_name = " ".join(first_name.split())[:255]
    email = claims.get("email")
    if (
        claims.get("email_verified") is True
        and isinstance(email, str)
        and email.strip()
    ):
        normalized_email = email.strip().lower()[:255]
        email_owner_id = await session.scalar(
            select(User.id).where(
                func.lower(User.email) == normalized_email,
                User.id != user.id,
            )
        )
        if email_owner_id is None:
            user.email = normalized_email

    user.last_active_at = datetime.now(UTC)
    await session.flush()
    return user


# best-effort superapp resolution from a bearer token. Returns None (never
# raises) when the bridge is disabled or the token is not a valid superapp
# token, so the caller can fall back to native Flutter auth.
async def try_superapp_user(
    authorization: str | None, session: AsyncSession
) -> User | None:
    if not superapp_bridge_enabled():
        return None
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = decode_superapp_token(token)
    except jwt.InvalidTokenError:
        return None
    except Exception:  # pragma: no cover - defensive, never break the request
        logger.warning("superapp token verification raised unexpectedly")
        return None

    user = await resolve_or_create_superapp_user(session, claims)
    if user is None:
        return None
    # the token verified as a genuine superapp identity, so a blocked account is
    # a hard denial — do not fall through to native auth
    if user.is_blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account suspended")
    return user
