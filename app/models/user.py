from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Identity, Index, String, UniqueConstraint, text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.analytics import EventAnalytics
    from app.models.club import Club
    from app.models.event import Event
    from app.models.favorite import Favorite
    from app.models.moderation import ModerationLog
    from app.models.reminder import Reminder
    from app.models.rating import Rating
    from app.models.comment import Comment
    from app.models.code import EmailVerificationCode
    from app.models.password_reset import PasswordResetCode
    from app.models.friend import PrivacySettings


# stores telegram user profiles
class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
        Index("ix_users_telegram_id", "telegram_id"),
        Index(
            "uq_users_verified_email",
            "email",
            unique=True,
            postgresql_where=text("is_verified = true"),
            sqlite_where=text("is_verified = 1"),
        ),
        Index(
            "uq_users_verified_nickname",
            "nickname",
            unique=True,
            postgresql_where=text("is_verified = true"),
            sqlite_where=text("is_verified = 1"),
        ),
    )

    # core telegram identity fields
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(16))
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_moderator: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    photo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # authentication & nu profile fields
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    nickname: Mapped[str | None] = mapped_column(String(24), nullable=True)

    # admin and moderation fields
    role: Mapped[str] = mapped_column(String(32), default="user", server_default="'user'")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    blocked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_by_admin_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # links users to owned and created records
    owned_clubs: Mapped[list[Club]] = relationship(back_populates="owner")
    created_events: Mapped[list[Event]] = relationship(
        back_populates="creator",
        foreign_keys="Event.creator_user_id",
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    favorites: Mapped[list[Favorite]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    moderation_logs: Mapped[list[ModerationLog]] = relationship(
        back_populates="moderator",
    )
    event_analytics: Mapped[list[EventAnalytics]] = relationship(back_populates="user")
    
    ratings: Mapped[list[Rating]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Rating.user_id",
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Comment.user_id",
    )
    verification_codes: Mapped[list[EmailVerificationCode]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_reset_codes: Mapped[list[PasswordResetCode]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    privacy_settings: Mapped[PrivacySettings | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
