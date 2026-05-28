from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models.user import User
from app.models.code import EmailVerificationCode
from app.models.password_reset import PasswordResetCode
from app.models.favorite import Favorite
from app.models.reminder import Reminder
from app.models.rating import Rating
from app.models.comment import Comment
from app.services.email import send_verification_email, send_password_reset_email
from app.services.security import hash_password, verify_password, validate_password_format, validate_nickname_format
from app.web.auth import MiniAppUser, require_miniapp_user, upsert_miniapp_user, create_session_token
from app.web.schemas import (
    UserRegisterRequest,
    UserVerifyRequest,
    UserResendRequest,
    UserLoginRequest,
    NicknameRequest,
    ProfileResponse,
    ProfileHistoryItem,
    ActionResponse,
    AuthResponse,
    ForgotPasswordRequestBody,
    ForgotPasswordVerifyBody,
    ForgotPasswordResetBody,
)

logger = logging.getLogger("app.web.routers.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

_RESET_RATE_LIMITS: dict[str, list[datetime]] = {}
_RESET_REQUEST_LIMIT = 5
_RESET_REQUEST_WINDOW = timedelta(hours=1)
_RESET_VERIFY_LIMIT = 20
_RESET_VERIFY_WINDOW = timedelta(minutes=15)


def generate_6digit_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _rate_limit_key(prefix: str, request: Request, email: str) -> str:
    return f"{prefix}:{_client_ip(request)}:{email[:255]}"


def _rate_limited(key: str, limit: int, window: timedelta, now: datetime) -> bool:
    cutoff = now - window
    hits = [ts for ts in _RESET_RATE_LIMITS.get(key, []) if ts > cutoff]
    if len(hits) >= limit:
        _RESET_RATE_LIMITS[key] = hits
        return True
    hits.append(now)
    _RESET_RATE_LIMITS[key] = hits
    return False


async def get_unique_nickname(session: AsyncSession, base: str) -> str:
    """Generates a unique nickname by appending digits if necessary."""
    # Clean nickname base
    clean = re.sub(r"[^a-zA-Z0-9_.]", "", base)[:20]
    if not clean:
        clean = "user"
    
    candidate = clean
    counter = 1
    while True:
        stmt = select(User).where(User.nickname == candidate, User.is_verified == True)
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            return candidate
        candidate = f"{clean[:18]}{counter}"
        counter += 1

import re


@router.post("/register", response_model=ActionResponse)
async def register(
    payload: UserRegisterRequest,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
    x_language: str | None = Header(default="en", alias="X-Language"),
    x_theme: str | None = Header(default="light", alias="X-Theme"),
) -> ActionResponse:
    # 1. Validate email domain
    email = payload.email.strip().lower()
    if not email.endswith("@nu.edu.kz"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only @nu.edu.kz addresses"
        )

    # 2. Check password format
    pwd_err = validate_password_format(payload.password)
    if pwd_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pwd_err)

    # 3. Check if email is already verified by another account
    stmt = select(User).where(User.email == email, User.is_verified == True)
    existing_verified = await session.execute(stmt)
    if existing_verified.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already registered. Please log in."
        )

    # Get or create current user corresponding to this Telegram ID
    user = await upsert_miniapp_user(session, miniapp_user)

    # Update unverified user registration details
    user.email = email
    user.password_hash = hash_password(payload.password)
    user.is_verified = False

    # 4. Generate & Send 6-digit code
    code = generate_6digit_code()
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.email_code_ttl_minutes)

    # Invalidate older codes for this user
    await session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    )

    # Save new code
    db_code = EmailVerificationCode(
        user_id=user.id,
        email=email,
        code_hash=hash_code(code),
        expires_at=expires_at,
    )
    session.add(db_code)
    await session.flush()

    # Send the email dispatch with language pref and theme
    send_verification_email(email, code, lang=x_language, theme=x_theme)

    await session.commit()
    return ActionResponse(
        ok=True,
        message=f"Verification code sent to {email}. Code expires in {settings.email_code_ttl_minutes} minutes."
    )


@router.post("/verify", response_model=AuthResponse)
async def verify(
    payload: UserVerifyRequest,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    email = payload.email.strip().lower()
    code_input = payload.code.strip()

    if len(code_input) != 6 or not code_input.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code must be exactly 6 digits."
        )

    user = await upsert_miniapp_user(session, miniapp_user)

    # Retrieve code
    stmt = select(EmailVerificationCode).where(
        EmailVerificationCode.user_id == user.id,
        EmailVerificationCode.email == email
    )
    result = await session.execute(stmt)
    db_code = result.scalar_one_or_none()

    if not db_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code found for this email. Please request a new code."
        )

    # Check attempts
    if db_code.attempts >= 5:
        await session.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.id == db_code.id)
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many failed verification attempts. Please request a new code."
        )

    # Check expiry
    now_utc = datetime.now(UTC)
    # Ensure expires_at is timezone-aware
    expires_at = db_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at < now_utc:
        await session.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.id == db_code.id)
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new code."
        )

    # Verify code
    hashed_input = hash_code(code_input)
    if not hmac.compare_digest(db_code.code_hash, hashed_input):
        db_code.attempts += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification code. Attempts remaining: {5 - db_code.attempts}."
        )

    # Verification successful!
    user.is_verified = True
    
    # Generate public nickname if not set
    if not user.nickname:
        base = email.split("@")[0]
        user.nickname = await get_unique_nickname(session, base)

    # Clean up verification code
    await session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.id == db_code.id)
    )

    await session.commit()

    # Return updated session JWT token and user info
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
        }
    )


@router.post("/resend", response_model=ActionResponse)
async def resend(
    payload: UserResendRequest,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
    x_language: str | None = Header(default="en", alias="X-Language"),
    x_theme: str | None = Header(default="light", alias="X-Theme"),
) -> ActionResponse:
    email = payload.email.strip().lower()
    user = await upsert_miniapp_user(session, miniapp_user)

    # Enforce 60 seconds resend cooldown
    stmt = select(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    result = await session.execute(stmt)
    existing_code = result.scalar_one_or_none()

    if existing_code:
        created_at = existing_code.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - created_at).total_seconds()
        settings = get_settings()
        cooldown = settings.email_resend_cooldown_seconds
        if elapsed < cooldown:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {int(cooldown - elapsed)} seconds before requesting a new code."
            )

    # Invalidate old codes
    await session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    )

    # Generate & Send new code
    code = generate_6digit_code()
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.email_code_ttl_minutes)

    db_code = EmailVerificationCode(
        user_id=user.id,
        email=email,
        code_hash=hash_code(code),
        expires_at=expires_at,
    )
    session.add(db_code)
    await session.flush()

    send_verification_email(email, code, lang=x_language, theme=x_theme)
    await session.commit()

    return ActionResponse(
        ok=True,
        message=f"A new verification code has been sent to {email}."
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: UserLoginRequest,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    email = payload.email.strip().lower()
    
    # 1. Fetch the verified user by email
    stmt = select(User).where(User.email == email, User.is_verified == True)
    result = await session.execute(stmt)
    verified_user = result.scalar_one_or_none()

    if not verified_user or not verified_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or password."
        )

    # 2. Verify password
    if not verify_password(payload.password, verified_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or password."
        )

    # 3. Link verified email account to current Telegram ID!
    current_guest_user = await upsert_miniapp_user(session, miniapp_user)

    if current_guest_user.id != verified_user.id:
        # Merge guest account details (favorites, reminders, ratings, comments) into the verified user!
        
        # 1. Favorites: delete duplicates from guest first
        existing_favs_stmt = select(Favorite.event_id).where(Favorite.user_id == verified_user.id)
        existing_favs_res = await session.execute(existing_favs_stmt)
        verified_fav_event_ids = set(existing_favs_res.scalars().all())
        if verified_fav_event_ids:
            await session.execute(
                delete(Favorite)
                .where(Favorite.user_id == current_guest_user.id, Favorite.event_id.in_(verified_fav_event_ids))
            )
        await session.execute(
            update(Favorite)
            .where(Favorite.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # 2. Reminders: delete duplicates from guest first
        existing_rems_stmt = select(Reminder.event_id, Reminder.offset_minutes).where(Reminder.user_id == verified_user.id)
        existing_rems_res = await session.execute(existing_rems_stmt)
        verified_rem_tuples = set(existing_rems_res.all())
        for event_id, offset_minutes in verified_rem_tuples:
            await session.execute(
                delete(Reminder)
                .where(
                    Reminder.user_id == current_guest_user.id,
                    Reminder.event_id == event_id,
                    Reminder.offset_minutes == offset_minutes
                )
            )
        await session.execute(
            update(Reminder)
            .where(Reminder.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # 3. Ratings: delete duplicates from guest first
        existing_ratings_stmt = select(Rating.event_id).where(Rating.user_id == verified_user.id)
        existing_ratings_res = await session.execute(existing_ratings_stmt)
        verified_rating_event_ids = set(existing_ratings_res.scalars().all())
        if verified_rating_event_ids:
            await session.execute(
                delete(Rating)
                .where(Rating.user_id == current_guest_user.id, Rating.event_id.in_(verified_rating_event_ids))
            )
        await session.execute(
            update(Rating)
            .where(Rating.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # 4. Comments: no unique constraints, safe to merge
        await session.execute(
            update(Comment)
            .where(Comment.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # Delete the guest user record A to make room for changing telegram_id
        await session.execute(delete(User).where(User.id == current_guest_user.id))
        await session.flush()

        # Update verified user's telegram ID
        verified_user.telegram_id = miniapp_user.id
        
        # Sync current metadata
        verified_user.username = miniapp_user.username
        verified_user.first_name = miniapp_user.first_name
        verified_user.last_name = miniapp_user.last_name
        verified_user.language_code = miniapp_user.language_code
        verified_user.is_bot = miniapp_user.is_bot

    await session.commit()

    return AuthResponse(
        token=create_session_token(miniapp_user),
        user={
            "id": verified_user.telegram_id,
            "username": verified_user.username,
            "first_name": verified_user.first_name,
            "last_name": verified_user.last_name,
            "email": verified_user.email,
            "nickname": verified_user.nickname,
            "is_verified": verified_user.is_verified,
        }
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification required to view profile."
        )

    # Fetch comments and ratings
    from sqlalchemy.orm import selectinload
    stmt = select(User).where(User.id == user.id).options(
        selectinload(User.comments).selectinload(Comment.event),
        selectinload(User.ratings).selectinload(Rating.event),
    )
    user_loaded = (await session.execute(stmt)).scalar_one()

    # Map ratings and comments by event_id for merging
    merged: dict[int, dict] = {}
    for r in user_loaded.ratings:
        merged[r.event_id] = {
            "event_token": r.event.public_token,
            "event_title": r.event.title,
            "rating_id": r.id,
            "score": r.score,
            "comment_id": None,
            "content": None,
            "created_at": r.created_at.isoformat(),
        }
    for c in user_loaded.comments:
        if c.event_id in merged:
            merged[c.event_id]["comment_id"] = c.id
            merged[c.event_id]["content"] = c.content
        else:
            merged[c.event_id] = {
                "event_token": c.event.public_token,
                "event_title": c.event.title,
                "rating_id": None,
                "score": None,
                "comment_id": c.id,
                "content": c.content,
                "created_at": c.created_at.isoformat(),
            }

    history = [
        ProfileHistoryItem(**val)
        for val in sorted(merged.values(), key=lambda x: x["created_at"], reverse=True)
    ]

    return ProfileResponse(
        email=user.email or "",
        nickname=user.nickname or "",
        is_verified=user.is_verified,
        history=history,
    )


@router.put("/profile/nickname", response_model=ActionResponse)
async def update_nickname(
    payload: NicknameRequest,
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    nickname = payload.nickname.strip()

    # Validate nickname format
    err = validate_nickname_format(nickname)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    user = await upsert_miniapp_user(session, miniapp_user)
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification required."
        )

    # Check if nickname is already taken by another verified user
    stmt = select(User).where(User.nickname == nickname, User.is_verified == True, User.id != user.id)
    existing = await session.execute(stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This nickname is already taken. Please choose another one."
        )

    user.nickname = nickname
    await session.commit()
    return ActionResponse(ok=True, message="Nickname updated successfully.")


@router.post("/profile/logout", response_model=ActionResponse)
async def logout(
    miniapp_user: MiniAppUser = Depends(require_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    return ActionResponse(ok=True, message="Successfully logged out.")


# ──────────────────────────────────────────────
# Forgot-password flow  (OWASP-compliant)
# ──────────────────────────────────────────────

# Generic message always returned from /request so email addresses
# (and domain restrictions) are never disclosed to the caller.
_GENERIC_RESET_MSG = "If this email exists, a reset code has been sent."
_GENERIC_INVALID_MSG = "Invalid or expired code."
_GENERIC_TOO_MANY_MSG = "Too many attempts. Try again later."


@router.post("/forgot-password/request", response_model=ActionResponse)
async def forgot_password_request(
    payload: ForgotPasswordRequestBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    """
    Step 1: user submits their email.
    Always returns the same generic success message regardless of
    whether the account exists or the domain matches – OWASP guideline.
    """
    import threading

    email = payload.email.strip().lower()
    now_utc = datetime.now(UTC)

    if _rate_limited(
        _rate_limit_key("forgot-request", request, email),
        _RESET_REQUEST_LIMIT,
        _RESET_REQUEST_WINDOW,
        now_utc,
    ):
        logger.warning("Password reset request rate-limited for ip=%s", _client_ip(request))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_GENERIC_TOO_MANY_MSG,
        )

    # Silently ignore non-NU addresses (never reveal this restriction).
    if not email.endswith("@nu.edu.kz"):
        return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)

    # Validate basic structure without revealing details.
    if len(email) > 255 or "@" not in email:
        return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)

    # Look up the verified account.
    stmt = select(User).where(User.email == email, User.is_verified == True)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    # No account → return generic OK (no enumeration).
    if not user:
        return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)

    # Check resend cooldown – look up any existing code for this user.
    stmt_existing = select(PasswordResetCode).where(
        PasswordResetCode.user_id == user.id
    ).order_by(PasswordResetCode.created_at.desc()).limit(1)
    result_existing = await session.execute(stmt_existing)
    existing_code = result_existing.scalar_one_or_none()

    if existing_code:
        resend_at = existing_code.resend_available_at
        if resend_at.tzinfo is None:
            resend_at = resend_at.replace(tzinfo=UTC)
        if now_utc < resend_at:
            logger.info("Password reset resend cooldown hit for user_id=%s", user.id)
            # Rate-limited by email cooldown — still return a generic 200.
            return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)

    # Generate a new 6-digit code and hash it.
    code = generate_6digit_code()
    code_hash = hash_code(code)

    settings = get_settings()
    expires_at = now_utc + timedelta(minutes=settings.email_code_ttl_minutes)
    resend_available_at = now_utc + timedelta(seconds=settings.email_resend_cooldown_seconds)

    # Invalidate any previous reset code for this user.
    await session.execute(
        delete(PasswordResetCode).where(PasswordResetCode.user_id == user.id)
    )

    db_code = PasswordResetCode(
        user_id=user.id,
        code_hash=code_hash,
        expires_at=expires_at,
        resend_available_at=resend_available_at,
        attempts_count=0,
    )
    session.add(db_code)
    await session.commit()

    # Send email in a background thread so the HTTP response is not blocked.
    # NOTE: the plain code must NEVER be logged here – only passed to the mailer.
    threading.Thread(
        target=send_password_reset_email,
        args=(email, code),
        daemon=True,
    ).start()

    return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)


@router.post("/forgot-password/verify", response_model=ActionResponse)
async def forgot_password_verify(
    payload: ForgotPasswordVerifyBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    """
    Step 2: user submits the 6-digit code to prove they control the email.
    Returns a generic OK on success.  Increments the attempt counter on
    failure; locks out after 5 wrong guesses.
    """
    email = payload.email.strip().lower()
    code_input = payload.code.strip()
    now_utc = datetime.now(UTC)

    if _rate_limited(
        _rate_limit_key("forgot-verify", request, email),
        _RESET_VERIFY_LIMIT,
        _RESET_VERIFY_WINDOW,
        now_utc,
    ):
        logger.warning("Password reset verification rate-limited for ip=%s", _client_ip(request))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_GENERIC_TOO_MANY_MSG,
        )

    # Validate input format early.
    if len(email) > 255 or len(code_input) != 6 or not code_input.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Generic response for unknown emails.
    stmt = select(User).where(User.email == email, User.is_verified == True)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    stmt_code = select(PasswordResetCode).where(
        PasswordResetCode.user_id == user.id,
        PasswordResetCode.used_at == None,  # noqa: E711
    ).order_by(PasswordResetCode.created_at.desc()).limit(1)
    result_code = await session.execute(stmt_code)
    db_code = result_code.scalar_one_or_none()

    if not db_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Check attempt count BEFORE verifying the hash.
    if db_code.attempts_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_GENERIC_TOO_MANY_MSG,
        )

    # Check expiry.
    expires_at = db_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Timing-safe comparison.
    hashed_input = hash_code(code_input)
    if not hmac.compare_digest(db_code.code_hash, hashed_input):
        db_code.attempts_count += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Code is valid — do NOT consume it here; that happens in /reset.
    return ActionResponse(ok=True, message="Code verified.")


@router.post("/forgot-password/reset", response_model=ActionResponse)
async def forgot_password_reset(
    payload: ForgotPasswordResetBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    """
    Step 3: user submits the verified code together with their new password.
    Atomically updates the password and marks the reset code as consumed.
    """
    email = payload.email.strip().lower()
    code_input = payload.code.strip()
    new_password = payload.new_password  # intentionally no .strip() here
    now_utc = datetime.now(UTC)

    if _rate_limited(
        _rate_limit_key("forgot-reset", request, email),
        _RESET_VERIFY_LIMIT,
        _RESET_VERIFY_WINDOW,
        now_utc,
    ):
        logger.warning("Password reset completion rate-limited for ip=%s", _client_ip(request))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_GENERIC_TOO_MANY_MSG,
        )

    # Reject leading/trailing whitespace in the new password.
    if new_password != new_password.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must not start or end with spaces.",
        )

    # Validate input format.
    if len(email) > 255 or len(code_input) != 6 or not code_input.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Validate password strength (8–128 chars).
    pwd_err = validate_password_format(new_password)
    if pwd_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pwd_err)

    # Look up the verified account.
    stmt = select(User).where(User.email == email, User.is_verified == True)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Retrieve the active (unused, non-expired) reset code.
    stmt_code = select(PasswordResetCode).where(
        PasswordResetCode.user_id == user.id,
        PasswordResetCode.used_at == None,  # noqa: E711
    ).order_by(PasswordResetCode.created_at.desc()).limit(1)
    result_code = await session.execute(stmt_code)
    db_code = result_code.scalar_one_or_none()

    if not db_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Enforce attempt cap.
    if db_code.attempts_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_GENERIC_TOO_MANY_MSG,
        )

    # Check expiry.
    expires_at = db_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Timing-safe code comparison.
    hashed_input = hash_code(code_input)
    if not hmac.compare_digest(db_code.code_hash, hashed_input):
        db_code.attempts_count += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # Atomically: update password + mark code as used.
    user.password_hash = hash_password(new_password)
    db_code.used_at = now_utc

    # Flush both writes before committing so they go out together.
    await session.flush()
    await session.commit()

    logger.info("Password reset completed for user_id=%s", user.id)
    return ActionResponse(ok=True, message="Password reset successfully.")
