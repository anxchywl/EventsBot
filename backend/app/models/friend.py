from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


# store one canonical row per friendship pair
class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (
        CheckConstraint("user_id < friend_user_id", name="friendship_order"),
        UniqueConstraint("user_id", "friend_user_id", name="uq_friendships_pair"),
        Index("ix_friendships_user_id", "user_id"),
        Index("ix_friendships_friend_user_id", "friend_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    friend_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    friend_user: Mapped[User] = relationship(foreign_keys=[friend_user_id])


# store directional requests before friendship creation
class FriendRequest(TimestampMixin, Base):
    __tablename__ = "friend_requests"
    __table_args__ = (
        CheckConstraint("requester_id <> recipient_id", name="friend_request_not_self"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled', 'expired')",
            name="friend_request_status",
        ),
        Index(
            "uq_friend_requests_pending_pair",
            "requester_id",
            "recipient_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index(
            "ix_friend_requests_recipient_status",
            "recipient_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_friend_requests_requester_status",
            "requester_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    invite_id: Mapped[int | None] = mapped_column(
        ForeignKey("friend_invites.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    recipient: Mapped[User] = relationship(foreign_keys=[recipient_id])
    invite: Mapped[FriendInvite | None] = relationship(back_populates="requests")


# store hashed invite links with expiry and revoke state
class FriendInvite(TimestampMixin, Base):
    __tablename__ = "friend_invites"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked', 'expired')", name="friend_invite_status"
        ),
        UniqueConstraint("token_hash", name="uq_friend_invites_token_hash"),
        Index("ix_friend_invites_owner_status", "owner_id", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(foreign_keys=[owner_id])
    requests: Mapped[list[FriendRequest]] = relationship(back_populates="invite")


# store friend visibility and contact preferences
class PrivacySettings(TimestampMixin, Base):
    __tablename__ = "privacy_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_privacy_settings_user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    show_favorites_to_friends: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    show_profile_to_friends: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    allow_friend_requests: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    user: Mapped[User] = relationship(
        back_populates="privacy_settings", foreign_keys=[user_id]
    )
