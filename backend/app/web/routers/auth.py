from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, UTC  # timedelta used for code expiry

from fastapi import APIRouter, Depends, HTTPException, status, Header
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
from app.models.friend import FriendInvite, FriendRequest, Friendship, PrivacySettings
from app.models.event import Event
from app.models.club import Club
from app.models.analytics import EventAnalytics
from app.models.moderation import ModerationLog
from app.models.chat import Chat
from app.models.audit import AuditLog, UserActivityLog
from app.services.email import send_verification_email, send_password_reset_email
from app.services.security import (
    hash_password,
    verify_password,
    validate_password_format,
    validate_nickname_format,
)
from app.services.friends import canonical_pair, friend_ids
from app.web.realtime import publish_miniapp_event
from app.web.auth import (
    MiniAppUser,
    create_session_token,
    effective_web_role,
    require_current_miniapp_user,
    upsert_miniapp_user,
)
from app.web.limiter import check_rate_limit
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

_GENERIC_TOO_MANY_MSG = "Too many attempts. Try again later."


# generate 6digit code
def generate_6digit_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


# hash code
def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


# build Redis rate-limit key scoped to email for forgot-password flow
def _rl_email_key(action: str, email: str) -> str:
    return f"rate:email:{email[:255]}:{action}"


# get unique nickname
async def get_unique_nickname(session: AsyncSession, base: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.]", "", base)[:20]
    if not clean:
        clean = "user"

    prefix = clean[:18]
    result = await session.execute(
        select(User.nickname).where(
            User.nickname.like(f"{prefix}%"),
            User.is_verified == True,
        )
    )
    taken = {row[0] for row in result}

    if clean not in taken:
        return clean
    for counter in range(1, 101):
        candidate = f"{prefix}{counter}"
        if candidate not in taken:
            return candidate
    # ultimate fallback when namespace is saturated
    return f"{clean[:12]}{secrets.token_hex(4)}"


# start email verification for a telegram user
@router.post("/register", response_model=ActionResponse)
async def register(
    payload: UserRegisterRequest,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
    x_language: str | None = Header(default="en", alias="X-Language"),
    x_theme: str | None = Header(default="light", alias="X-Theme"),
) -> ActionResponse:
    # 1. validate email domain
    email = payload.email.strip().lower()
    await check_rate_limit(
        f"rate:email:{email[:255]}:register", 3, 3600, _GENERIC_TOO_MANY_MSG
    )
    email_parts = email.split("@")
    if len(email_parts) != 2 or email_parts[1] != "nu.edu.kz":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Only @nu.edu.kz addresses"
        )

    # 2. check password format
    pwd_err = validate_password_format(payload.password)
    if pwd_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pwd_err)

    # 3. check if email is already verified by another account
    stmt = select(User).where(User.email == email, User.is_verified == True)
    existing_verified = await session.execute(stmt)
    if existing_verified.scalar_one_or_none():
        # owasp: return generic success to prevent account enumeration
        settings = get_settings()
        return ActionResponse(
            ok=True,
            message=f"Verification code sent to {email}. Code expires in {settings.email_code_ttl_minutes} minutes.",
        )

    # get or create current user corresponding to this telegram id
    user = await upsert_miniapp_user(session, miniapp_user)

    # update unverified user registration details
    user.email = email
    user.password_hash = hash_password(payload.password)
    user.is_verified = False

    # 4. generate & send 6-digit code
    code = generate_6digit_code()
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.email_code_ttl_minutes)

    # invalidate older codes for this user
    await session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    )

    # save new code
    db_code = EmailVerificationCode(
        user_id=user.id,
        email=email,
        code_hash=hash_code(code),
        expires_at=expires_at,
    )
    session.add(db_code)
    await session.flush()

    session.add(
        UserActivityLog(
            user_id=user.id, action="register", metadata_json={"email": email}
        )
    )
    await session.commit()

    # offload blocking SMTP call so it does not block the event loop
    asyncio.create_task(
        asyncio.to_thread(
            send_verification_email, email, code, lang=x_language, theme=x_theme
        )
    )

    return ActionResponse(
        ok=True,
        message=f"Verification code sent to {email}. Code expires in {settings.email_code_ttl_minutes} minutes.",
    )


# complete email verification and refresh profile data
@router.post("/verify", response_model=AuthResponse)
async def verify(
    payload: UserVerifyRequest,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    email = payload.email.strip().lower()
    code_input = payload.code.strip()

    if len(code_input) != 6 or not code_input.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code must be exactly 6 digits.",
        )

    user = await upsert_miniapp_user(session, miniapp_user)

    # retrieve code
    stmt = select(EmailVerificationCode).where(
        EmailVerificationCode.user_id == user.id, EmailVerificationCode.email == email
    )
    result = await session.execute(stmt)
    db_code = result.scalar_one_or_none()

    if not db_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code found for this email. Please request a new code.",
        )

    # check attempts
    if db_code.attempts >= 5:
        await session.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.id == db_code.id)
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many failed verification attempts. Please request a new code.",
        )

    # check expiry
    now_utc = datetime.now(UTC)
    # ensure expires_at is timezone-aware
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
            detail="Verification code has expired. Please request a new code.",
        )

    # verify code
    hashed_input = hash_code(code_input)
    if not hmac.compare_digest(db_code.code_hash, hashed_input):
        db_code.attempts += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    # verification successful
    user.is_verified = True

    # generate public nickname if not set
    if not user.nickname:
        base = email.split("@")[0]
        user.nickname = await get_unique_nickname(session, base)

    # clean up verification code
    await session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.id == db_code.id)
    )

    session.add(
        UserActivityLog(
            user_id=user.id, action="email_verified", metadata_json={"email": email}
        )
    )
    await session.commit()

    # return updated session jwt token and user info
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


# resend verification code within cooldown limits
@router.post("/resend", response_model=ActionResponse)
async def resend(
    payload: UserResendRequest,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
    x_language: str | None = Header(default="en", alias="X-Language"),
    x_theme: str | None = Header(default="light", alias="X-Theme"),
) -> ActionResponse:
    email = payload.email.strip().lower()
    user = await upsert_miniapp_user(session, miniapp_user)

    # enforce 60 seconds resend cooldown
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
                detail=f"Please wait {int(cooldown - elapsed)} seconds before requesting a new code.",
            )

    # invalidate old codes
    await session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    )

    # generate & send new code
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

    await session.commit()

    asyncio.create_task(
        asyncio.to_thread(
            send_verification_email, email, code, lang=x_language, theme=x_theme
        )
    )

    return ActionResponse(
        ok=True, message=f"A new verification code has been sent to {email}."
    )


# move guest social data onto the verified account
async def merge_friend_records(
    session: AsyncSession,
    *,
    guest_user_id: int,
    verified_user_id: int,
) -> None:
    friendship_rows = list(
        (
            await session.execute(
                select(Friendship).where(
                    (Friendship.user_id == guest_user_id)
                    | (Friendship.friend_user_id == guest_user_id)
                )
            )
        )
        .scalars()
        .all()
    )
    for row in friendship_rows:
        other_id = row.friend_user_id if row.user_id == guest_user_id else row.user_id
        if other_id == verified_user_id:
            await session.delete(row)
            continue
        first_id, second_id = canonical_pair(verified_user_id, other_id)
        duplicate = await session.scalar(
            select(Friendship).where(
                Friendship.id != row.id,
                Friendship.user_id == first_id,
                Friendship.friend_user_id == second_id,
            )
        )
        if duplicate is not None:
            await session.delete(row)
        else:
            row.user_id = first_id
            row.friend_user_id = second_id

    request_rows = list(
        (
            await session.execute(
                select(FriendRequest).where(
                    (FriendRequest.requester_id == guest_user_id)
                    | (FriendRequest.recipient_id == guest_user_id)
                )
            )
        )
        .scalars()
        .all()
    )
    for row in request_rows:
        next_requester_id = (
            verified_user_id if row.requester_id == guest_user_id else row.requester_id
        )
        next_recipient_id = (
            verified_user_id if row.recipient_id == guest_user_id else row.recipient_id
        )
        if next_requester_id == next_recipient_id:
            await session.delete(row)
            continue
        if row.status == "pending":
            duplicate = await session.scalar(
                select(FriendRequest).where(
                    FriendRequest.id != row.id,
                    FriendRequest.status == "pending",
                    FriendRequest.requester_id == next_requester_id,
                    FriendRequest.recipient_id == next_recipient_id,
                )
            )
            if duplicate is not None:
                await session.delete(row)
                continue
        row.requester_id = next_requester_id
        row.recipient_id = next_recipient_id

    await session.execute(
        update(FriendInvite)
        .where(FriendInvite.owner_id == guest_user_id)
        .values(owner_id=verified_user_id)
    )

    verified_privacy = await session.scalar(
        select(PrivacySettings).where(PrivacySettings.user_id == verified_user_id)
    )
    guest_privacy = await session.scalar(
        select(PrivacySettings).where(PrivacySettings.user_id == guest_user_id)
    )
    if guest_privacy is not None:
        if verified_privacy is None:
            guest_privacy.user_id = verified_user_id
        else:
            await session.delete(guest_privacy)


# link a verified email account to the current telegram user
@router.post("/login", response_model=AuthResponse)
async def login(
    payload: UserLoginRequest,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    email = payload.email.strip().lower()
    await check_rate_limit(
        f"rate:email:{email[:255]}:login", 10, 3600, _GENERIC_TOO_MANY_MSG
    )

    # 1. fetch the verified user by email
    stmt = select(User).where(User.email == email, User.is_verified == True)
    result = await session.execute(stmt)
    verified_user = result.scalar_one_or_none()

    if not verified_user or not verified_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email or password."
        )

    # 2. verify password
    if not verify_password(payload.password, verified_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email or password."
        )

    # 3. check if the user is blocked
    settings = get_settings()
    is_admin = miniapp_user.id in settings.admin_ids
    if verified_user.is_blocked and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been blocked.",
        )

    # 4. link verified email account to current telegram id
    current_guest_user = await upsert_miniapp_user(session, miniapp_user)

    if current_guest_user.id != verified_user.id:
        # merge guest account details (favorites, reminders, ratings, comments) into the verified user

        # 1. favorites: delete duplicates from guest first
        existing_favs_stmt = select(Favorite.event_id).where(
            Favorite.user_id == verified_user.id
        )
        existing_favs_res = await session.execute(existing_favs_stmt)
        verified_fav_event_ids = set(existing_favs_res.scalars().all())
        if verified_fav_event_ids:
            await session.execute(
                delete(Favorite).where(
                    Favorite.user_id == current_guest_user.id,
                    Favorite.event_id.in_(verified_fav_event_ids),
                )
            )
        await session.execute(
            update(Favorite)
            .where(Favorite.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # 2. reminders: delete duplicates from guest first
        existing_rems_stmt = select(Reminder.event_id, Reminder.offset_minutes).where(
            Reminder.user_id == verified_user.id
        )
        existing_rems_res = await session.execute(existing_rems_stmt)
        verified_rem_tuples = set(existing_rems_res.all())
        for event_id, offset_minutes in verified_rem_tuples:
            await session.execute(
                delete(Reminder).where(
                    Reminder.user_id == current_guest_user.id,
                    Reminder.event_id == event_id,
                    Reminder.offset_minutes == offset_minutes,
                )
            )
        await session.execute(
            update(Reminder)
            .where(Reminder.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # 3. ratings: delete duplicates from guest first
        existing_ratings_stmt = select(Rating.event_id).where(
            Rating.user_id == verified_user.id
        )
        existing_ratings_res = await session.execute(existing_ratings_stmt)
        verified_rating_event_ids = set(existing_ratings_res.scalars().all())
        if verified_rating_event_ids:
            await session.execute(
                delete(Rating).where(
                    Rating.user_id == current_guest_user.id,
                    Rating.event_id.in_(verified_rating_event_ids),
                )
            )
        await session.execute(
            update(Rating)
            .where(Rating.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # 4. comments: no unique constraints, safe to merge
        await session.execute(
            update(Comment)
            .where(Comment.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # 5. events: merge created events and approvals
        await session.execute(
            update(Event)
            .where(Event.creator_user_id == current_guest_user.id)
            .values(creator_user_id=verified_user.id)
        )
        await session.execute(
            update(Event)
            .where(Event.approved_by_user_id == current_guest_user.id)
            .values(approved_by_user_id=verified_user.id)
        )

        # 6. clubs: merge owned clubs
        await session.execute(
            update(Club)
            .where(Club.owner_user_id == current_guest_user.id)
            .values(owner_user_id=verified_user.id)
        )

        # 7. eventanalytics: merge interactions
        await session.execute(
            update(EventAnalytics)
            .where(EventAnalytics.user_id == current_guest_user.id)
            .values(user_id=verified_user.id)
        )

        # 8. moderationlog: merge logs
        await session.execute(
            update(ModerationLog)
            .where(ModerationLog.actor_user_id == current_guest_user.id)
            .values(actor_user_id=verified_user.id)
        )

        # 9. chats: merge created chats
        await session.execute(
            update(Chat)
            .where(Chat.created_by_user_id == current_guest_user.id)
            .values(created_by_user_id=verified_user.id)
        )

        await merge_friend_records(
            session,
            guest_user_id=current_guest_user.id,
            verified_user_id=verified_user.id,
        )

        # delete the guest user record a to make room for changing telegram_id
        await session.delete(current_guest_user)
        await session.flush()

        # update verified user's telegram id
        verified_user.telegram_id = miniapp_user.id

        # sync current metadata
        verified_user.username = miniapp_user.username
        verified_user.first_name = miniapp_user.first_name
        verified_user.last_name = miniapp_user.last_name
        verified_user.language_code = miniapp_user.language_code
        verified_user.is_bot = miniapp_user.is_bot

    session.add(
        UserActivityLog(
            user_id=verified_user.id, action="login", metadata_json={"email": email}
        )
    )
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
            "role": effective_web_role(verified_user, miniapp_user.id),
            "is_blocked": verified_user.is_blocked,
            "blocked_reason": verified_user.blocked_reason,
        },
    )


# get profile
@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    user = await upsert_miniapp_user(session, miniapp_user)
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification required to view profile.",
        )

    # fetch comments and ratings
    from sqlalchemy.orm import selectinload

    stmt = (
        select(User)
        .where(User.id == user.id)
        .options(
            selectinload(User.comments).selectinload(Comment.event),
            selectinload(User.ratings).selectinload(Rating.event),
        )
    )
    user_loaded = (await session.execute(stmt)).scalar_one()

    # map ratings and comments by event_id for merging
    merged: dict[int, dict] = {}
    for r in user_loaded.ratings:
        if not r.event or r.event.status != "approved":
            continue
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
        if not c.event or c.event.status != "approved":
            continue
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
        is_blocked=user.is_blocked,
        blocked_reason=user.blocked_reason,
        history=history,
    )


# update nickname
@router.put("/profile/nickname", response_model=ActionResponse)
async def update_nickname(
    payload: NicknameRequest,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    nickname = payload.nickname.strip()

    # validate nickname format
    err = validate_nickname_format(nickname)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    user = await upsert_miniapp_user(session, miniapp_user)
    await check_rate_limit(
        f"rate:user:{miniapp_user.id}:nickname", 5, 3600, _GENERIC_TOO_MANY_MSG
    )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Verification required."
        )

    # check if nickname is already taken by another verified user
    stmt = select(User).where(
        User.nickname == nickname, User.is_verified == True, User.id != user.id
    )
    existing = await session.execute(stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This nickname is already taken. Please choose another one.",
        )

    user.nickname = nickname
    try:
        await session.commit()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This nickname is already taken. Please choose another one.",
        )
    await publish_miniapp_event(
        "friend_profile_changed",
        {
            "user_id": user.id,
            "nickname": user.nickname,
            "target_user_ids": list(await friend_ids(session, user.id)) + [user.id],
        },
    )
    return ActionResponse(ok=True, message="Nickname updated successfully.")


# unlink the web session from telegram identity
@router.post("/profile/logout", response_model=ActionResponse)
async def logout(
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    stmt = select(User).where(User.telegram_id == miniapp_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user and user.is_verified:
        # unlink by setting telegram_id to negative value (since it is not null and unique)
        user.telegram_id = -user.telegram_id
        await session.commit()
    return ActionResponse(ok=True, message="Successfully logged out.")


# forgot-password flow avoids account enumeration


# keep reset responses generic so emails and domain rules are not leaked
_GENERIC_RESET_MSG = "If this email exists, a reset code has been sent."
_GENERIC_INVALID_MSG = "Invalid or expired code."


# start reset flow without revealing account existence
@router.post("/forgot-password/request", response_model=ActionResponse)
async def forgot_password_request(
    payload: ForgotPasswordRequestBody,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
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

    await check_rate_limit(
        _rl_email_key("fp_request", email), 5, 3600, _GENERIC_TOO_MANY_MSG
    )

    # hide domain policy from callers
    if not email.endswith("@nu.edu.kz"):
        return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)

    # reject malformed email without changing the response shape
    if len(email) > 255 or "@" not in email:
        return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)

    # look up the verified account
    stmt = select(User).where(User.email == email, User.is_verified == True)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    # hide whether the account exists
    if not user:
        return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)

    # enforce per-account resend cooldown
    stmt_existing = (
        select(PasswordResetCode)
        .where(PasswordResetCode.user_id == user.id)
        .order_by(PasswordResetCode.created_at.desc())
        .limit(1)
    )
    result_existing = await session.execute(stmt_existing)
    existing_code = result_existing.scalar_one_or_none()

    if existing_code:
        resend_at = existing_code.resend_available_at
        if resend_at.tzinfo is None:
            resend_at = resend_at.replace(tzinfo=UTC)
        if now_utc < resend_at:
            logger.info("Password reset resend cooldown hit for user_id=%s", user.id)
            # preserve the same external response during cooldown
            return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)

    # hash the email code before storage
    code = generate_6digit_code()
    code_hash = hash_code(code)

    settings = get_settings()
    expires_at = now_utc + timedelta(minutes=settings.email_code_ttl_minutes)
    resend_available_at = now_utc + timedelta(
        seconds=settings.email_resend_cooldown_seconds
    )

    # keep only one active reset code per user
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

    # pass the plain code only to the mailer — task is tracked by the event loop, not a daemon thread
    asyncio.create_task(asyncio.to_thread(send_password_reset_email, email, code))

    return ActionResponse(ok=True, message=_GENERIC_RESET_MSG)


# verify reset code without consuming it
@router.post("/forgot-password/verify", response_model=ActionResponse)
async def forgot_password_verify(
    payload: ForgotPasswordVerifyBody,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
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

    await check_rate_limit(
        _rl_email_key("fp_verify", email), 20, 900, _GENERIC_TOO_MANY_MSG
    )

    # reject malformed input before querying reset state
    if len(email) > 255 or len(code_input) != 6 or not code_input.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # avoid revealing whether the email is registered
    stmt = select(User).where(User.email == email, User.is_verified == True)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    stmt_code = (
        select(PasswordResetCode)
        .where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.used_at == None,  # noqa: E711
        )
        .order_by(PasswordResetCode.created_at.desc())
        .limit(1)
    )
    result_code = await session.execute(stmt_code)
    db_code = result_code.scalar_one_or_none()

    if not db_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # stop brute-force attempts before hash comparison
    if db_code.attempts_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_GENERIC_TOO_MANY_MSG,
        )

    # reject expired reset codes
    expires_at = db_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # compare hashes without timing leaks
    hashed_input = hash_code(code_input)
    if not hmac.compare_digest(db_code.code_hash, hashed_input):
        db_code.attempts_count += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # mark this code as verified so the reset step can confirm verify was called
    db_code.verified_at = now_utc
    await session.commit()
    return ActionResponse(ok=True, message="Code verified.")


# consume reset code and replace the password
@router.post("/forgot-password/reset", response_model=ActionResponse)
async def forgot_password_reset(
    payload: ForgotPasswordResetBody,
    miniapp_user: MiniAppUser = Depends(require_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    """
    Step 3: user submits the verified code together with their new password.
    Atomically updates the password and marks the reset code as consumed.
    """
    email = payload.email.strip().lower()
    code_input = payload.code.strip()
    new_password = payload.new_password  # preserve whitespace for explicit validation
    now_utc = datetime.now(UTC)

    await check_rate_limit(
        _rl_email_key("fp_reset", email), 20, 900, _GENERIC_TOO_MANY_MSG
    )

    # reject accidental whitespace without silently changing the password
    if new_password != new_password.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must not start or end with spaces.",
        )

    # reject malformed input before querying reset state
    if len(email) > 255 or len(code_input) != 6 or not code_input.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # reuse the normal password rules
    pwd_err = validate_password_format(new_password)
    if pwd_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pwd_err)

    # look up the verified account
    stmt = select(User).where(User.email == email, User.is_verified == True)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # only unused reset codes can complete password changes
    stmt_code = (
        select(PasswordResetCode)
        .where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.used_at == None,  # noqa: E711
        )
        .order_by(PasswordResetCode.created_at.desc())
        .limit(1)
    )
    result_code = await session.execute(stmt_code)
    db_code = result_code.scalar_one_or_none()

    if not db_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # require that the verify step was completed before allowing a reset
    if not db_code.verified_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # enforce that verify → reset happens within 10 minutes to prevent delayed replay
    verified_at = db_code.verified_at
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    if (now_utc - verified_at).total_seconds() > 600:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # stop brute-force attempts before hash comparison
    if db_code.attempts_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_GENERIC_TOO_MANY_MSG,
        )

    # reject expired reset codes
    expires_at = db_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # compare hashes without timing leaks
    hashed_input = hash_code(code_input)
    if not hmac.compare_digest(db_code.code_hash, hashed_input):
        db_code.attempts_count += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_INVALID_MSG,
        )

    # update password and consume the code in one transaction
    user.password_hash = hash_password(new_password)
    db_code.used_at = now_utc

    # invalidate active miniapp sessions after password reset
    user.telegram_id = -abs(user.telegram_id)

    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="password_reset",
            target_type="user",
            target_id=str(user.id),
        )
    )

    # flush both writes before committing together
    await session.flush()
    await session.commit()

    logger.info("Password reset completed for user_id=%s", user.id)
    return ActionResponse(ok=True, message="Password reset successfully.")
