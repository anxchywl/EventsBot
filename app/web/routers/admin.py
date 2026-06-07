from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import or_, select, func, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.user import User
from app.models.event import Event
from app.config import get_settings
from app.models.audit import AuditLog
from app.models.chat import Chat
from app.services.chats import connected_group_status
from app.services.events import get_event_by_public_token
from app.services.reviews import invalidate_review_caches, permanently_delete_review
from app.web.realtime import publish_review_deleted
from app.web.auth import effective_web_role, require_admin_or_moderator, require_admin
from app.web.routers.events import validate_public_token
from app.web.schemas import ActionResponse

logger = logging.getLogger("app.web.routers.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.delete("/reviews/{event_id}/{user_id}", response_model=ActionResponse)
async def admin_delete_review(
    event_id: int = Path(..., ge=1),
    user_id: int = Path(..., ge=1),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    event = await session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    result = await permanently_delete_review(
        session,
        event=event,
        target_user_id=user_id,
        admin=admin,
    )
    if not result["deleted"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review already deleted")
    await session.commit()
    invalidate_review_caches()
    await publish_review_deleted(result)

    return ActionResponse(ok=True, message="Review deleted successfully by admin.")


@router.delete("/reviews/by-token/{public_token}/{user_id}", response_model=ActionResponse)
async def admin_delete_review_by_token(
    public_token: str,
    user_id: int = Path(..., ge=1),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    public_token = validate_public_token(public_token)
    event = await get_event_by_public_token(session, public_token)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    result = await permanently_delete_review(
        session,
        event=event,
        target_user_id=user_id,
        admin=admin,
    )
    if not result["deleted"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review already deleted")
    await session.commit()
    invalidate_review_caches()
    await publish_review_deleted(result)

    return ActionResponse(ok=True, message="Review deleted successfully by admin.")


from pydantic import BaseModel, Field, field_validator
from typing import Any

class AdminStatsResponse(BaseModel):
    total_bot_users: int
    total_miniapp_users: int
    total_nu_accounts: int
    total_blocked: int

class AdminUserItem(BaseModel):
    id: int
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None
    nickname: str | None
    role: str
    has_nu_account: bool
    is_verified: bool
    is_blocked: bool
    registered_date: str
    last_active_date: str | None

class AuditLogItem(BaseModel):
    id: int
    actor_id: int | None
    action: str
    target_type: str | None
    target_id: str | None
    created_at: str
    metadata_json: Any | None

class ConnectedGroupItem(BaseModel):
    id: int
    telegram_chat_id: int
    title: str | None
    username: str | None
    chat_type: str
    invite_link: str | None
    member_count: int | None
    connected_at: str | None
    last_activity_at: str | None
    removed_at: str | None
    registration_status: str
    status: str
    permissions: dict[str, Any]
    categories_selected: bool
    dashboard_message_id: int | None
    setup_message_id: int | None

class ConnectedGroupsSummary(BaseModel):
    total_groups: int
    active: int
    setup_required: int
    missing_permissions: int

class ConnectedGroupsResponse(BaseModel):
    summary: ConnectedGroupsSummary
    groups: list[ConnectedGroupItem]

class BlockUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if len(email) > 255 or "@" not in email:
            raise ValueError("Invalid email")
        return email

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        reason = value.strip()
        return reason or None

@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    admin: User = Depends(require_admin_or_moderator),
    session: AsyncSession = Depends(get_session),
) -> AdminStatsResponse:
    bot_users = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
    miniapp_users = bot_users
    nu_accounts = (await session.execute(select(func.count()).select_from(User).where(User.is_verified == True))).scalar() or 0
    blocked_users = (await session.execute(select(func.count()).select_from(User).where(User.is_blocked == True))).scalar() or 0

    return AdminStatsResponse(
        total_bot_users=bot_users,
        total_miniapp_users=miniapp_users,
        total_nu_accounts=nu_accounts,
        total_blocked=blocked_users,
    )


@router.get("/connected-groups", response_model=ConnectedGroupsResponse)
async def list_connected_groups(
    q: str | None = Query(default=None, max_length=100),
    status_filter: str | None = Query(default=None, max_length=32),
    sort: str = Query("newest", max_length=32),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=5000),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ConnectedGroupsResponse:
    current_bot_id = _current_bot_id()
    stmt = (
        select(Chat)
        .where(
            Chat.chat_type.in_(("group", "supergroup", "channel")),
            Chat.is_active.is_(True),
            Chat.registration_status != "inactive",
            Chat.removed_at.is_(None),
        )
        .options(selectinload(Chat.dashboard_message))
    )
    if current_bot_id is not None:
        stmt = stmt.where(Chat.bot_id == current_bot_id)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Chat.title.ilike(needle),
                Chat.username.ilike(needle),
                Chat.telegram_chat_id.cast(String).ilike(needle),
                func.abs(Chat.telegram_chat_id).cast(String).ilike(needle),
            )
        )

    chats = list((await session.execute(stmt)).scalars().all())
    groups = [_connected_group_item(chat) for chat in chats]

    allowed_statuses = {"active", "setup_required", "missing_permissions"}
    if status_filter in allowed_statuses:
        groups = [group for group in groups if group.status == status_filter]

    if sort == "oldest":
        groups.sort(key=lambda group: group.connected_at or "")
    elif sort == "most_active":
        groups.sort(key=lambda group: group.last_activity_at or "", reverse=True)
    elif sort == "newest":
        groups.sort(key=lambda group: group.connected_at or "", reverse=True)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid sort")

    summary_counts = {
        "active": 0,
        "setup_required": 0,
        "missing_permissions": 0,
    }
    for chat in chats:
        status_name = connected_group_status(chat)
        summary_counts[status_name] = summary_counts.get(status_name, 0) + 1

    return ConnectedGroupsResponse(
        summary=ConnectedGroupsSummary(
            total_groups=len(chats),
            active=summary_counts["active"],
            setup_required=summary_counts["setup_required"],
            missing_permissions=summary_counts["missing_permissions"],
        ),
        groups=groups[offset : offset + limit],
    )


def _connected_group_item(chat: Chat) -> ConnectedGroupItem:
    permissions = chat.permissions_status or {}
    return ConnectedGroupItem(
        id=chat.id,
        telegram_chat_id=chat.telegram_chat_id,
        title=chat.title,
        username=chat.username,
        chat_type=chat.chat_type,
        invite_link=chat.invite_link,
        member_count=chat.member_count,
        connected_at=chat.connected_at.isoformat() if chat.connected_at else None,
        last_activity_at=chat.last_activity_at.isoformat() if chat.last_activity_at else None,
        removed_at=chat.removed_at.isoformat() if chat.removed_at else None,
        registration_status=chat.registration_status,
        status=connected_group_status(chat),
        permissions=permissions,
        categories_selected=chat.categories_selected,
        dashboard_message_id=chat.dashboard_message.message_id if chat.dashboard_message else None,
        setup_message_id=chat.setup_message_id,
    )


def _current_bot_id() -> int | None:
    token = get_settings().bot_token.get_secret_value()
    bot_id, _, _ = token.partition(":")
    try:
        return int(bot_id)
    except ValueError:
        return None

@router.post("/users/block", response_model=ActionResponse)
async def block_user(
    payload: BlockUserRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = (await session.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="Admins cannot block other admins")
    
    user.is_blocked = True
    user.blocked_reason = payload.reason
    user.blocked_at = datetime.now()
    user.blocked_by_admin_id = admin.id

    audit_log = AuditLog(
        actor_user_id=admin.id,
        action="block_user",
        target_type="user",
        target_id=str(user.id),
        metadata_json={"reason": payload.reason, "email": payload.email}
    )
    session.add(audit_log)
    await session.commit()
    return ActionResponse(ok=True, message=f"User {payload.email} blocked successfully.")

@router.post("/users/unblock", response_model=ActionResponse)
async def unblock_user(
    payload: BlockUserRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = (await session.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_blocked = False
    user.blocked_reason = None
    user.blocked_at = None
    user.blocked_by_admin_id = None

    audit_log = AuditLog(
        actor_user_id=admin.id,
        action="unblock_user",
        target_type="user",
        target_id=str(user.id),
        metadata_json={"email": payload.email}
    )
    session.add(audit_log)
    await session.commit()
    return ActionResponse(ok=True, message=f"User {payload.email} unblocked successfully.")

@router.get("/users", response_model=list[AdminUserItem])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=5000),
    q: str | None = Query(default=None, max_length=100),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminUserItem]:
    stmt = select(User).order_by(User.last_active_at.desc().nullslast(), User.created_at.desc())
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(needle),
                User.nickname.ilike(needle),
                User.username.ilike(needle),
                User.first_name.ilike(needle),
                User.last_name.ilike(needle),
                User.telegram_id.cast(String).ilike(needle),
                func.abs(User.telegram_id).cast(String).ilike(needle),
            )
        )
    stmt = stmt.limit(limit).offset(offset)
    users = (await session.execute(stmt)).scalars().all()
    
    settings = get_settings()
    return [
        AdminUserItem(
            id=u.id,
            telegram_id=abs(u.telegram_id),
            username=u.username,
            first_name=u.first_name,
            last_name=u.last_name,
            email=u.email,
            nickname=u.nickname,
            role=effective_web_role(u, abs(u.telegram_id)),
            has_nu_account=bool(u.email),
            is_verified=u.is_verified,
            is_blocked=u.is_blocked,
            registered_date=u.created_at.isoformat(),
            last_active_date=u.last_active_at.isoformat() if u.last_active_at else None
        ) for u in users
    ]


@router.get("/audit-logs", response_model=list[AuditLogItem])
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=5000),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLogItem]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    logs = (await session.execute(stmt)).scalars().all()
    
    return [
        AuditLogItem(
            id=log.id,
            actor_id=log.actor_user_id,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            created_at=log.created_at.isoformat(),
            metadata_json=log.metadata_json
        ) for log in logs
    ]
