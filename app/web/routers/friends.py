from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from aiogram import Bot
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.config import get_settings
from app.models.enums import EventStatus
from app.models.event import Event
from app.models.friend import FriendInvite, FriendRequest, Friendship, PrivacySettings
from app.models.user import User
from app.services.friends import (
    accept_friend_request,
    create_friend_invite,
    create_friend_request,
    ensure_privacy_settings,
    event_friends_going,
    expire_stale_friend_rows,
    friend_ids,
    get_active_invite_by_token,
    invite_url,
    public_user_summary,
    revoke_active_invites_for_pair,
    display_name,
)
from app.services.telegram_links import (
    build_telegram_miniapp_invite_link,
    build_telegram_share_link,
)
from app.web.telegram import get_bot_username
from app.web.auth import MiniAppUser, effective_web_role, optional_current_miniapp_user, require_verified_user, upsert_miniapp_user
from app.web.realtime import publish_miniapp_event
from app.web.schemas import (
    ActionResponse,
    FriendActionResponse,
    FriendInviteLookupResponse,
    FriendInviteResponse,
    FriendRequestCreate,
    FriendRequestItem,
    FriendRequestsResponse,
    FriendSearchResponse,
    FriendsListResponse,
    EventFriendGoing,
    PrivacySettingsResponse,
    PrivacySettingsUpdate,
)


router = APIRouter(prefix="/api/friends", tags=["miniapp-friends"])
logger = logging.getLogger("app.web.routers.friends")

_FRIEND_RATE_LIMITS: dict[str, list[float]] = {}
_INVITE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


def _validate_invite_token(token: str | None) -> str:
    value = (token or "").strip()
    if not _INVITE_TOKEN_RE.fullmatch(value):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite expired or revoked.")
    return value


def _client_key(request: Request, user: User, action: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{action}:{user.id}:{host}"


def _check_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    now = time.time()
    cutoff = now - window_seconds
    hits = [ts for ts in _FRIEND_RATE_LIMITS.get(key, []) if ts > cutoff]
    if len(hits) >= limit:
        _FRIEND_RATE_LIMITS[key] = hits
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests")
    hits.append(now)
    _FRIEND_RATE_LIMITS[key] = hits

    # Prevent memory leaks by pruning stale keys when dict grows large
    if len(_FRIEND_RATE_LIMITS) > 10000:
        for k in list(_FRIEND_RATE_LIMITS.keys()):
            _FRIEND_RATE_LIMITS[k] = [ts for ts in _FRIEND_RATE_LIMITS[k] if ts > cutoff]
            if not _FRIEND_RATE_LIMITS[k]:
                del _FRIEND_RATE_LIMITS[k]

def _notify_user(user: User | None, message: str) -> None:
    if user is None or not user.telegram_id or user.telegram_id < 0:
        return
    asyncio.create_task(_send_telegram_notification(user.telegram_id, message))


async def _send_telegram_notification(telegram_id: int, message: str) -> None:
    bot = Bot(token=get_settings().bot_token.get_secret_value())
    try:
        await bot.send_message(telegram_id, message)
    except Exception as exc:
        logger.info("failed to send friend notification to %s: %s", telegram_id, exc)
    finally:
        await bot.session.close()


@router.get("", response_model=FriendsListResponse)
async def list_friends(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=5000),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> FriendsListResponse:
    await expire_stale_friend_rows(session)
    ids = await friend_ids(session, user.id)
    if not ids:
        return FriendsListResponse(total=0, friends=[])
    result = await session.execute(
        select(User)
        .where(User.id.in_(ids), User.is_verified.is_(True))
        .order_by(func.lower(User.nickname), func.lower(User.email))
    )
    friends = list(result.scalars().all())[offset : offset + limit]
    return FriendsListResponse(
        total=len(friends),
        friends=[
            await public_user_summary(session, friend, current_user=user)
            for friend in friends
        ],
    )


@router.get("/requests", response_model=FriendRequestsResponse)
async def list_friend_requests(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=5000),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> FriendRequestsResponse:
    await expire_stale_friend_rows(session)
    result = await session.execute(
        select(FriendRequest)
        .where(
            FriendRequest.status == "pending",
            or_(
                FriendRequest.requester_id == user.id,
                FriendRequest.recipient_id == user.id,
            ),
        )
        .order_by(FriendRequest.created_at.desc())
    )
    requests = list(result.scalars().all())[offset : offset + limit]
    incoming: list[FriendRequestItem] = []
    outgoing: list[FriendRequestItem] = []
    for request_row in requests:
        other_id = request_row.requester_id if request_row.recipient_id == user.id else request_row.recipient_id
        other = await session.get(User, other_id)
        if other is None or not other.is_verified:
            continue
        item = FriendRequestItem(
            id=request_row.id,
            status=request_row.status,
            created_at=request_row.created_at.isoformat(),
            expires_at=request_row.expires_at.isoformat(),
            user=await public_user_summary(session, other, current_user=user),
        )
        if request_row.recipient_id == user.id:
            incoming.append(item)
        else:
            outgoing.append(item)
    return FriendRequestsResponse(incoming=incoming, outgoing=outgoing)


@router.post("/requests", response_model=FriendActionResponse)
async def send_friend_request(
    payload: FriendRequestCreate,
    request: Request,
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> FriendActionResponse:
    _check_rate_limit(_client_key(request, user, "friend-request"), limit=20, window_seconds=3600)
    invite: FriendInvite | None = None
    recipient: User | None = None
    if payload.invite_token:
        invite = await get_active_invite_by_token(session, _validate_invite_token(payload.invite_token))
        if invite is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite expired or revoked.")
        recipient = await session.get(User, invite.owner_id)
    elif payload.user_id:
        recipient = await session.get(User, payload.user_id)
    if recipient is None or not recipient.is_verified:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    friend_request = await create_friend_request(session, user, recipient, invite=invite)
    await session.commit()
    requester_name = display_name(user)
    _notify_user(recipient, f"{requester_name} sent you a friend request.")
    await publish_miniapp_event(
        "friend_request_received",
        {
            "request_id": friend_request.id,
            "from_user_id": user.id,
            "to_user_id": recipient.id,
            "target_user_ids": [recipient.id, user.id],
            "notification": f"{requester_name} sent you a friend request.",
        },
    )
    return FriendActionResponse(ok=True, message="Friend request sent.", request_id=friend_request.id)


@router.post("/requests/{request_id}/accept", response_model=ActionResponse)
async def accept_request(
    request_id: int = Path(..., ge=1),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    request_row = await session.get(FriendRequest, request_id)
    if request_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Friend request not found.")
    await accept_friend_request(session, request_row, recipient=user)
    requester_id = request_row.requester_id
    requester = await session.get(User, requester_id)
    await session.commit()
    accepter_name = display_name(user)
    requester_name = display_name(requester) if requester is not None else "this NU student"
    _notify_user(requester, f"You and {accepter_name} are now friends.")
    _notify_user(user, f"You and {requester_name} are now friends.")
    await publish_miniapp_event(
        "friend_request_accepted",
        {
            "request_id": request_id,
            "from_user_id": requester_id,
            "to_user_id": user.id,
            "target_user_ids": [requester_id, user.id],
            "notification": f"You and {accepter_name} are now friends.",
        },
    )
    return ActionResponse(ok=True, message="Friend request accepted.")


@router.post("/requests/{request_id}/decline", response_model=ActionResponse)
async def decline_request(
    request_id: int = Path(..., ge=1),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    request_row = await session.get(FriendRequest, request_id)
    if request_row is None or request_row.recipient_id != user.id or request_row.status != "pending":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Friend request not found.")
    request_row.status = "declined"
    request_row.responded_at = datetime.now(UTC)
    requester_id = request_row.requester_id
    requester = await session.get(User, requester_id)
    await session.commit()
    decliner_name = display_name(user)
    _notify_user(requester, f"{decliner_name} declined your friend request.")
    await publish_miniapp_event(
        "friend_request_declined",
        {
            "request_id": request_id,
            "from_user_id": requester_id,
            "to_user_id": user.id,
            "target_user_ids": [requester_id, user.id],
            "notification": f"{decliner_name} declined your friend request.",
        },
    )
    return ActionResponse(ok=True, message="Friend request declined.")


@router.post("/requests/{request_id}/cancel", response_model=ActionResponse)
async def cancel_request(
    request_id: int = Path(..., ge=1),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    request_row = await session.get(FriendRequest, request_id)
    if request_row is None or request_row.requester_id != user.id or request_row.status != "pending":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Friend request not found.")
    request_row.status = "cancelled"
    request_row.responded_at = datetime.now(UTC)
    recipient_id = request_row.recipient_id
    await session.commit()
    await publish_miniapp_event(
        "friend_request_cancelled",
        {
            "request_id": request_id,
            "from_user_id": user.id,
            "to_user_id": recipient_id,
            "target_user_ids": [recipient_id, user.id],
        },
    )
    return ActionResponse(ok=True, message="Friend request cancelled.")


@router.delete("/{friend_user_id}", response_model=ActionResponse)
async def remove_friend(
    friend_user_id: int = Path(..., ge=1),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    first_id, second_id = (user.id, friend_user_id) if user.id < friend_user_id else (friend_user_id, user.id)
    friendship = await session.scalar(
        select(Friendship).where(
            Friendship.user_id == first_id,
            Friendship.friend_user_id == second_id,
        )
    )
    if friendship is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Friendship not found.")
    await session.delete(friendship)
    await revoke_active_invites_for_pair(session, user.id, friend_user_id)
    friend_user = await session.get(User, friend_user_id)
    await session.commit()
    _notify_user(friend_user, "A friend removed you from their NU Events friends.")
    await publish_miniapp_event(
        "friend_removed",
        {
            "from_user_id": user.id,
            "to_user_id": friend_user_id,
            "target_user_ids": [user.id, friend_user_id],
            "notification": "A friendship was removed.",
        },
    )
    return ActionResponse(ok=True, message="Friend removed.")


@router.get("/search", response_model=FriendSearchResponse)
async def search_users(
    request: Request,
    q: str = Query("", min_length=0, max_length=100),
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> FriendSearchResponse:
    if effective_web_role(user, user.telegram_id) != "admin":
        _check_rate_limit(_client_key(request, user, "friend-search"), limit=90, window_seconds=60)
    query = q.strip().lower()
    if len(query) < 2:
        return FriendSearchResponse(results=[], page=page, limit=limit, has_more=False)
    stmt = (
        select(User)
        .outerjoin(PrivacySettings, PrivacySettings.user_id == User.id)
        .where(
            User.id != user.id,
            User.is_verified.is_(True),
            or_(
                PrivacySettings.id.is_(None),
                PrivacySettings.allow_friend_requests.is_(True),
            ),
            or_(
                func.lower(User.nickname).like(f"%{query}%"),
                func.lower(User.email).like(f"%{query}%"),
            ),
        )
        .order_by(func.lower(User.nickname), func.lower(User.email))
        .offset((page - 1) * limit)
        .limit(limit + 1)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return FriendSearchResponse(
        results=[
            await public_user_summary(session, found_user, current_user=user)
            for found_user in rows[:limit]
        ],
        page=page,
        limit=limit,
        has_more=len(rows) > limit,
    )


@router.post("/invites", response_model=FriendInviteResponse)
async def create_invite(
    request: Request,
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> FriendInviteResponse:
    if effective_web_role(user, user.telegram_id) != "admin":
        _check_rate_limit(_client_key(request, user, "friend-invite"), limit=60, window_seconds=3600)
    invite, token = await create_friend_invite(session, user)
    await session.commit()
    
    bot_name = await get_bot_username()
    direct_link = build_telegram_miniapp_invite_link(
        bot_username=bot_name,
        miniapp_short_name=get_settings().telegram_miniapp_short_name,
        token=token,
    ) or invite_url(token)
    
    inviter_name = display_name(user)
    message_text = (
        f"{inviter_name} invited you to be friends on NU Events! "
        f"See which events your friends are attending and coordinate plans."
    )
    share_url = build_telegram_share_link(
        url=direct_link,
        text=message_text,
    )
    
    return FriendInviteResponse(
        id=invite.id,
        token=token,
        url=direct_link,
        share_url=share_url,
        expires_at=invite.expires_at.isoformat(),
    )


@router.delete("/invites/{invite_id}", response_model=ActionResponse)
async def revoke_invite(
    invite_id: int = Path(..., ge=1),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    invite = await session.get(FriendInvite, invite_id)
    if invite is None or invite.owner_id != user.id or invite.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found.")
    invite.status = "revoked"
    invite.revoked_at = datetime.now(UTC)
    await session.commit()
    return ActionResponse(ok=True, message="Invite revoked.")


@router.get("/invites/{token}", response_model=FriendInviteLookupResponse)
async def lookup_invite(
    token: str,
    miniapp_user: MiniAppUser | None = Depends(optional_current_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> FriendInviteLookupResponse:
    invite = await get_active_invite_by_token(session, _validate_invite_token(token))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite expired or revoked.")
    
    owner = await session.get(User, invite.owner_id)
    if owner is None or not owner.is_verified:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite expired or revoked.")
        
    if miniapp_user is None:
        inviter = await public_user_summary(session, owner, current_user=None)
        await session.commit()
        return FriendInviteLookupResponse(state="requires_start", inviter=inviter)
        
    current_user = await upsert_miniapp_user(session, miniapp_user)
    
    if not current_user.is_verified:
        inviter = await public_user_summary(session, owner, current_user=None)
        await session.commit()
        return FriendInviteLookupResponse(state="requires_verification", inviter=inviter)
        
    inviter = await public_user_summary(session, owner, current_user=current_user)
    await session.commit()
    return FriendInviteLookupResponse(
        state="ready",
        inviter=inviter,
    )


@router.get("/settings", response_model=PrivacySettingsResponse)
async def get_privacy_settings(
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> PrivacySettingsResponse:
    settings = await ensure_privacy_settings(session, user)
    await session.commit()
    return PrivacySettingsResponse(
        show_favorites_to_friends=settings.show_favorites_to_friends,
        show_profile_to_friends=settings.show_profile_to_friends,
        allow_friend_requests=settings.allow_friend_requests,
    )


@router.put("/settings", response_model=PrivacySettingsResponse)
async def update_privacy_settings(
    payload: PrivacySettingsUpdate,
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> PrivacySettingsResponse:
    settings = await ensure_privacy_settings(session, user)
    for key in ("show_favorites_to_friends", "show_profile_to_friends", "allow_friend_requests"):
        value = getattr(payload, key)
        if value is not None:
            setattr(settings, key, value)
    await session.commit()
    await publish_miniapp_event(
        "privacy_settings_changed",
        {
            "user_id": user.id,
            "target_user_ids": list(await friend_ids(session, user.id)) + [user.id],
        },
    )
    return PrivacySettingsResponse(
        show_favorites_to_friends=settings.show_favorites_to_friends,
        show_profile_to_friends=settings.show_profile_to_friends,
        allow_friend_requests=settings.allow_friend_requests,
    )


@router.get("/events/{event_id}/friends-going", response_model=list[EventFriendGoing])
async def event_friends(
    event_id: int = Path(..., ge=1),
    user: User = Depends(require_verified_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventFriendGoing]:
    event = await session.get(Event, event_id)
    if event is None or event.status != EventStatus.APPROVED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return await event_friends_going(session, user, event_id)
