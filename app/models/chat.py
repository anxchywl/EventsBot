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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.event import EventCategory, EventDetailMessage


# stores telegram chats that receive dashboards
class Chat(TimestampMixin, Base):
    __tablename__ = "chats"
    # enforce chat identity and type values
    __table_args__ = (
        CheckConstraint(
            "chat_type IN ('private', 'group', 'supergroup', 'channel')",
            name="chat_type",
        ),
        UniqueConstraint("telegram_chat_id", name="uq_chats_telegram_chat_id"),
        Index("ix_chats_telegram_chat_id", "telegram_chat_id"),
    )

    # telegram chat fields
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    chat_type: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    registration_message_id: Mapped[int | None] = mapped_column(BigInteger)

    # links chat to dashboard and category settings
    category_settings: Mapped[list[ChatCategorySetting]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )
    dashboard_message: Mapped[DashboardMessage | None] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        uselist=False,
    )
    event_detail_messages: Mapped[list[EventDetailMessage]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )


# stores which categories are enabled in a chat
class ChatCategorySetting(TimestampMixin, Base):
    __tablename__ = "chat_category_settings"
    # prevent duplicate settings per chat and category
    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "category_id",
            name="uq_chat_category_settings_chat_id_category_id",
        ),
    )

    # setting fields
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    category_id: Mapped[int] = mapped_column(
        ForeignKey("event_categories.id", ondelete="CASCADE"),
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    # links setting to chat and category
    chat: Mapped[Chat] = relationship(back_populates="category_settings")
    category: Mapped[EventCategory] = relationship(back_populates="chat_settings")


# stores the pinned dashboard message for a chat
class DashboardMessage(TimestampMixin, Base):
    __tablename__ = "dashboard_messages"

    # dashboard message tracking fields
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        unique=True,
    )
    message_id: Mapped[int] = mapped_column(BigInteger)
    last_rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_render_hash: Mapped[str | None] = mapped_column(String(128))

    # links dashboard message to its chat
    chat: Mapped[Chat] = relationship(back_populates="dashboard_message")
