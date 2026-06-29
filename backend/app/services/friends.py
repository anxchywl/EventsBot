from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Iterable
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.favorite import Favorite
from app.models.friend import FriendInvite, FriendRequest, Friendship, PrivacySettings
from app.models.user import User


FRIEND_REQUEST_TTL = timedelta(days=30)
FRIEND_INVITE_TTL = timedelta(days=7)


# store invite tokens as hashes only
def invite_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# keep friendship rows unique regardless of direction
def canonical_pair(user_id: int, other_user_id: int) -> tuple[int, int]:
    if user_id == other_user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot friend yourself.")
    return (
        (user_id, other_user_id)
        if user_id < other_user_id
        else (other_user_id, user_id)
    )


# derive a public display name without exposing raw ids
def display_name(user: User) -> str:
    name_part = user.nickname
    if not name_part and user.email:
        name_part = user.email.split("@")[0]
    if not name_part:
        name_part = user.username or "NU student"

    if name_part and "." in name_part:
        parts = name_part.split(".")
        if len(parts) == 2:
            first = parts[0].capitalize()
            second = parts[1].capitalize()
            return f"{first} {second}"
    return name_part.capitalize() if name_part else "Unknown"


# prefer telegram photos and fall back to initials
def avatar_payload(user: User) -> dict[str, str | None]:
    name = display_name(user)
    initials = "".join(
        part[:1] for part in name.replace("_", " ").replace(".", " ").split()[:2]
    ).upper()
    if getattr(user, "photo_url", None):
        url = user.photo_url
    else:
        url = None
        if user.telegram_id and user.telegram_id > 0:
            version = (
                user.photo_updated_at.isoformat()
                if user.photo_updated_at
                else str(user.telegram_id)
            )
            url = f"/api/events/avatar/{user.telegram_id}?{urlencode({'v': version})}"
    return {
        "url": url,
        "initials": initials[:2] or "NU",
    }


# expose direct telegram links only for allowed users
def telegram_url(user: User) -> str | None:
    if user.username:
        return f"https://t.me/{user.username}"
    if user.telegram_id and user.telegram_id > 0:
        return f"tg://user?id={user.telegram_id}"
    return None


# create privacy defaults on first access
async def ensure_privacy_settings(session: AsyncSession, user: User) -> PrivacySettings:
    settings = await session.scalar(
        select(PrivacySettings).where(PrivacySettings.user_id == user.id)
    )
    if settings is None:
        settings = PrivacySettings(user_id=user.id)
        session.add(settings)
        await session.flush()
    return settings


# expire pending social rows before reads and writes
async def expire_stale_friend_rows(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    await session.execute(
        update(FriendRequest)
        .where(FriendRequest.status == "pending", FriendRequest.expires_at < now)
        .values(status="expired", responded_at=now)
    )
    await session.execute(
        update(FriendInvite)
        .where(FriendInvite.status == "active", FriendInvite.expires_at < now)
        .values(status="expired")
    )


# check friendship through the canonical pair
async def are_friends(session: AsyncSession, user_id: int, other_user_id: int) -> bool:
    first_id, second_id = canonical_pair(user_id, other_user_id)
    return bool(
        await session.scalar(
            select(
                exists().where(
                    Friendship.user_id == first_id,
                    Friendship.friend_user_id == second_id,
                )
            )
        )
    )


# return both sides of canonical friendship rows
async def friend_ids(session: AsyncSession, user_id: int) -> set[int]:
    result = await session.execute(
        select(Friendship.user_id, Friendship.friend_user_id).where(
            or_(Friendship.user_id == user_id, Friendship.friend_user_id == user_id)
        )
    )
    ids: set[int] = set()
    for left_id, right_id in result.all():
        ids.add(right_id if left_id == user_id else left_id)
    return ids


# count friendships where the user is on either side
async def friend_count(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(Friendship.id)).where(
                or_(Friendship.user_id == user_id, Friendship.friend_user_id == user_id)
            )
        )
        or 0
    )


# count friendships for many users in one query
async def friend_counts(
    session: AsyncSession, user_ids: Iterable[int]
) -> dict[int, int]:
    ids = set(user_ids)
    if not ids:
        return {}
    result = await session.execute(
        select(Friendship.user_id, Friendship.friend_user_id).where(
            or_(Friendship.user_id.in_(ids), Friendship.friend_user_id.in_(ids))
        )
    )
    counts = {user_id: 0 for user_id in ids}
    for left_id, right_id in result.all():
        if left_id in counts:
            counts[left_id] += 1
        if right_id in counts:
            counts[right_id] += 1
    return counts


# compare friend sets for one profile
async def mutual_friend_count(
    session: AsyncSession, user_id: int, other_user_id: int
) -> int:
    if user_id == other_user_id:
        return 0
    left = await friend_ids(session, user_id)
    right = await friend_ids(session, other_user_id)
    return len(left & right)


# compute mutual counts without per-user queries
async def mutual_friend_counts(
    session: AsyncSession,
    current_user_id: int,
    target_user_ids: Iterable[int],
) -> dict[int, int]:
    targets = set(target_user_ids)
    if not targets:
        return {}
    current_friends = await friend_ids(session, current_user_id)
    counts = {target_id: 0 for target_id in targets}
    if not current_friends:
        return counts
    result = await session.execute(
        select(Friendship.user_id, Friendship.friend_user_id).where(
            or_(Friendship.user_id.in_(targets), Friendship.friend_user_id.in_(targets))
        )
    )
    for left_id, right_id in result.all():
        if left_id in targets and right_id in current_friends:
            counts[left_id] += 1
        if right_id in targets and left_id in current_friends:
            counts[right_id] += 1
    return counts


# expose request direction for profile actions
async def friendship_status(
    session: AsyncSession,
    current_user_id: int,
    target_user_id: int,
) -> tuple[str, int | None]:
    if current_user_id == target_user_id:
        return "self", None
    if await are_friends(session, current_user_id, target_user_id):
        return "friends", None
    request = await session.scalar(
        select(FriendRequest).where(
            FriendRequest.status == "pending",
            or_(
                and_(
                    FriendRequest.requester_id == current_user_id,
                    FriendRequest.recipient_id == target_user_id,
                ),
                and_(
                    FriendRequest.requester_id == target_user_id,
                    FriendRequest.recipient_id == current_user_id,
                ),
            ),
        )
    )
    if request is None:
        return "none", None
    if request.requester_id == current_user_id:
        return "outgoing_pending", request.id
    return "incoming_pending", request.id


# shape user data according to relationship privacy
async def public_user_summary(
    session: AsyncSession,
    target: User,
    *,
    current_user: User | None = None,
) -> dict:
    target_counts = await friend_counts(session, [target.id])
    mutual_count = (
        await mutual_friend_count(session, current_user.id, target.id)
        if current_user is not None
        else 0
    )
    relationship, request_id = (
        await friendship_status(session, current_user.id, target.id)
        if current_user is not None
        else ("none", None)
    )
    can_contact_directly = relationship in {"self", "friends"}
    return {
        "id": target.id,
        "nickname": display_name(target),
        "email": None,
        "avatar": avatar_payload(target),
        "friend_count": target_counts.get(target.id, 0),
        "mutual_friends_count": mutual_count,
        "telegram_url": telegram_url(target) if can_contact_directly else None,
        "relationship_status": relationship,
        "request_id": request_id,
    }


# create a short-lived invite without storing the raw token
async def create_friend_invite(
    session: AsyncSession, owner: User
) -> tuple[FriendInvite, str]:
    token = secrets.token_urlsafe(32)
    invite = FriendInvite(
        owner_id=owner.id,
        token_hash=invite_token_hash(token),
        expires_at=datetime.now(UTC) + FRIEND_INVITE_TTL,
    )
    session.add(invite)
    await session.flush()
    return invite, token


# resolve only active unexpired invites
async def get_active_invite_by_token(
    session: AsyncSession, token: str
) -> FriendInvite | None:
    await expire_stale_friend_rows(session)
    return await session.scalar(
        select(FriendInvite).where(
            FriendInvite.token_hash == invite_token_hash(token),
            FriendInvite.status == "active",
            FriendInvite.expires_at >= datetime.now(UTC),
        )
    )


# enforce verification, privacy, and duplicate request rules
async def create_friend_request(
    session: AsyncSession,
    requester: User,
    recipient: User,
    *,
    invite: FriendInvite | None = None,
) -> FriendRequest:
    await expire_stale_friend_rows(session)
    if not requester.is_verified or not recipient.is_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Nazarbayev University email verification required",
        )
    if requester.id == recipient.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot friend yourself.")
    if await are_friends(session, requester.id, recipient.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already friends.")
    recipient_privacy = await ensure_privacy_settings(session, recipient)
    if not recipient_privacy.allow_friend_requests:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This user is not accepting friend requests."
        )

    existing = await session.scalar(
        select(FriendRequest).where(
            FriendRequest.status == "pending",
            or_(
                and_(
                    FriendRequest.requester_id == requester.id,
                    FriendRequest.recipient_id == recipient.id,
                ),
                and_(
                    FriendRequest.requester_id == recipient.id,
                    FriendRequest.recipient_id == requester.id,
                ),
            ),
        )
    )
    if existing is not None:
        if existing.requester_id == requester.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Friend request already sent."
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This user already sent you a friend request."
        )

    request = FriendRequest(
        requester_id=requester.id,
        recipient_id=recipient.id,
        invite_id=invite.id if invite else None,
        expires_at=datetime.now(UTC) + FRIEND_REQUEST_TTL,
    )
    session.add(request)
    await session.flush()
    return request


# accept one request and cancel duplicates for the same pair
async def accept_friend_request(
    session: AsyncSession,
    request: FriendRequest,
    *,
    recipient: User,
) -> Friendship:
    await expire_stale_friend_rows(session)
    if request.status != "pending" or request.recipient_id != recipient.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Friend request not found.")
    if request.expires_at < datetime.now(UTC):
        request.status = "expired"
        request.responded_at = datetime.now(UTC)
        await session.flush()
        raise HTTPException(status.HTTP_410_GONE, "Friend request expired.")

    first_id, second_id = canonical_pair(request.requester_id, request.recipient_id)
    friendship = await session.scalar(
        select(Friendship).where(
            Friendship.user_id == first_id,
            Friendship.friend_user_id == second_id,
        )
    )
    if friendship is None:
        friendship = Friendship(user_id=first_id, friend_user_id=second_id)
        session.add(friendship)

    now = datetime.now(UTC)
    request.status = "accepted"
    request.responded_at = now
    await session.execute(
        update(FriendRequest)
        .where(
            FriendRequest.id != request.id,
            FriendRequest.status == "pending",
            or_(
                and_(
                    FriendRequest.requester_id == request.requester_id,
                    FriendRequest.recipient_id == request.recipient_id,
                ),
                and_(
                    FriendRequest.requester_id == request.recipient_id,
                    FriendRequest.recipient_id == request.requester_id,
                ),
            ),
        )
        .values(status="cancelled", responded_at=now)
    )
    await session.flush()
    return friendship


# prevent stale invite links after friendship removal
async def revoke_active_invites_for_pair(
    session: AsyncSession, first_user_id: int, second_user_id: int
) -> None:
    await session.execute(
        update(FriendInvite)
        .where(
            FriendInvite.status == "active",
            FriendInvite.owner_id.in_([first_user_id, second_user_id]),
        )
        .values(status="revoked", revoked_at=datetime.now(UTC))
    )


# show friends attending only when their privacy allows it
async def event_friends_going(
    session: AsyncSession, user: User | None, event_id: int
) -> list[dict]:
    if user is None:
        return []
    ids = await friend_ids(session, user.id)
    if not ids:
        return []
    result = await session.execute(
        select(User)
        .join(Favorite, Favorite.user_id == User.id)
        .outerjoin(PrivacySettings, PrivacySettings.user_id == User.id)
        .where(
            User.id.in_(ids),
            User.is_verified.is_(True),
            Favorite.event_id == event_id,
            or_(
                PrivacySettings.id.is_(None),
                PrivacySettings.show_favorites_to_friends.is_(True),
            ),
        )
        .order_by(func.lower(User.nickname), func.lower(User.email))
    )
    friends = list(result.scalars().all())
    counts = await friend_counts(session, [friend.id for friend in friends])
    mutuals = await mutual_friend_counts(
        session, user.id, [friend.id for friend in friends]
    )
    return [
        {
            "id": friend.id,
            "nickname": display_name(friend),
            "avatar": avatar_payload(friend),
            "friend_count": counts.get(friend.id, 0),
            "mutual_friends_count": mutuals.get(friend.id, 0),
            "telegram_url": telegram_url(friend),
        }
        for friend in friends
    ]


# batch friends-going data for event lists
async def bulk_event_friends_going(
    session: AsyncSession, user: User | None, event_ids: list[int]
) -> dict[int, list[dict]]:
    if user is None or not event_ids:
        return {event_id: [] for event_id in event_ids}
    ids = await friend_ids(session, user.id)
    if not ids:
        return {event_id: [] for event_id in event_ids}

    result = await session.execute(
        select(Favorite.event_id, User)
        .join(User, User.id == Favorite.user_id)
        .outerjoin(PrivacySettings, PrivacySettings.user_id == User.id)
        .where(
            User.id.in_(ids),
            User.is_verified.is_(True),
            Favorite.event_id.in_(event_ids),
            or_(
                PrivacySettings.id.is_(None),
                PrivacySettings.show_favorites_to_friends.is_(True),
            ),
        )
        .order_by(Favorite.event_id, func.lower(User.nickname), func.lower(User.email))
    )

    event_friends_map = {event_id: [] for event_id in event_ids}
    all_friends = {}
    for event_id, friend in result.all():
        event_friends_map[event_id].append(friend)
        all_friends[friend.id] = friend

    if not all_friends:
        return {event_id: [] for event_id in event_ids}

    counts = await friend_counts(session, list(all_friends.keys()))
    mutuals = await mutual_friend_counts(session, user.id, list(all_friends.keys()))

    return {
        event_id: [
            {
                "id": friend.id,
                "nickname": display_name(friend),
                "avatar": avatar_payload(friend),
                "friend_count": counts.get(friend.id, 0),
                "mutual_friends_count": mutuals.get(friend.id, 0),
                "telegram_url": telegram_url(friend),
            }
            for friend in friends
        ]
        for event_id, friends in event_friends_map.items()
    }


# build a mini app invite path when no base url is configured
def invite_url(token: str) -> str:
    base_url = (get_settings().miniapp_base_url or "").rstrip("/")
    path = f"/friends/invite/{token}"
    return f"{base_url}{path}" if base_url else path
