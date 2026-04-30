from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.event import EventCategory, EventDetailMessage


class Chat(TimestampMixin, Base):
    __tablename__ = "chats"
    __table_args__ = (
        CheckConstraint(
            "chat_type IN ('private', 'group', 'supergroup', 'channel')",
            name="chat_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    chat_type: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )

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
    )


class ChatCategorySetting(TimestampMixin, Base):
    __tablename__ = "chat_category_settings"
    __table_args__ = (
        UniqueConstraint("chat_id", "category_id", name="uq_chat_category_settings_chat_id_category_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    category_id: Mapped[int] = mapped_column(
        ForeignKey("event_categories.id", ondelete="CASCADE"),
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    chat: Mapped[Chat] = relationship(back_populates="category_settings")
    category: Mapped[EventCategory] = relationship(back_populates="chat_settings")


class DashboardMessage(TimestampMixin, Base):
    __tablename__ = "dashboard_messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        unique=True,
    )
    message_id: Mapped[int] = mapped_column(BigInteger)
    last_rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_render_hash: Mapped[str | None] = mapped_column(String(128))

    chat: Mapped[Chat] = relationship(back_populates="dashboard_message")
