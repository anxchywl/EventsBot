from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select, func, update, delete, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.user import User
from app.models.event import Event
from app.models.rating import Rating
from app.models.comment import Comment
from app.config import get_settings
from app.models.audit import AuditLog
from app.web.auth import effective_web_role, require_admin_or_moderator, require_admin
from app.web.schemas import ActionResponse

logger = logging.getLogger("app.web.routers.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.delete("/reviews/{event_id}/{user_id}", response_model=ActionResponse)
async def admin_delete_review(
    event_id: int,
    user_id: int,
    admin: User = Depends(require_admin_or_moderator),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    # Soft delete rating
    await session.execute(
        update(Rating)
        .where(Rating.event_id == event_id, Rating.user_id == user_id)
        .values(deleted_at=datetime.now(), deleted_by_user_id=admin.id)
    )
    # Soft delete comment
    await session.execute(
        update(Comment)
        .where(Comment.event_id == event_id, Comment.user_id == user_id)
        .values(deleted_at=datetime.now(), deleted_by_user_id=admin.id)
    )
    
    # Audit Log
    audit_log = AuditLog(
        actor_user_id=admin.id,
        action="delete_review",
        target_type="review",
        target_id=f"{event_id}:{user_id}",
        metadata_json={"event_id": event_id, "user_id": user_id}
    )
    session.add(audit_log)

    await session.commit()
    from app.web.routers.events import event_cache
    event_cache.clear()
    
    return ActionResponse(ok=True, message="Review deleted successfully by admin.")


from pydantic import BaseModel
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

class BlockUserRequest(BaseModel):
    email: str
    reason: str | None = None


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

@router.post("/users/block", response_model=ActionResponse)
async def block_user(
    payload: BlockUserRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    user = (await session.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
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
    limit: int = 1000,
    offset: int = 0,
    q: str | None = None,
    admin: User = Depends(require_admin_or_moderator),
    session: AsyncSession = Depends(get_session),
) -> list[AdminUserItem]:
    limit = max(1, min(limit, 2000))
    offset = max(0, offset)
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
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin_or_moderator),
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
