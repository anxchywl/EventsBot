from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import EventStatus

if TYPE_CHECKING:
    from app.models.analytics import EventAnalytics
    from app.models.chat import Chat, ChatCategorySetting
    from app.models.club import Club
    from app.models.favorite import Favorite
    from app.models.moderation import ModerationLog
    from app.models.reminder import Reminder
    from app.models.user import User
    from app.models.rating import Rating
    from app.models.comment import Comment


# stores event category metadata
class EventCategory(TimestampMixin, Base):
    __tablename__ = "event_categories"

    # category identity and ordering
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")

    # links categories to events and chat settings
    events: Mapped[list[Event]] = relationship(back_populates="category")
    chat_settings: Mapped[list[ChatCategorySetting]] = relationship(
        back_populates="category",
    )


# stores submitted events and update drafts
class Event(TimestampMixin, Base):
    __tablename__ = "events"
    # enforce status values and common lookup indexes
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'archived', 'rejected', 'needs_changes', 'cancelled')",
            name="status",
        ),
        Index(
            "ix_events_category_date_time", "category_id", "event_date", "event_time"
        ),
        Index("ix_events_status_date_time", "status", "event_date", "event_time"),
        Index("ix_events_public_token", "public_token", unique=True),
    )

    # event identity and ownership
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    parent_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
    )
    creator_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL")
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("event_categories.id", ondelete="RESTRICT"),
    )
    public_token: Mapped[str] = mapped_column(
        String(36),
        default=lambda: str(uuid4()),
        nullable=False,
    )
    # public event content
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    event_date: Mapped[date] = mapped_column(Date)
    event_time: Mapped[time] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Almaty", server_default="Asia/Almaty"
    )
    location: Mapped[str] = mapped_column(String(255))
    organizer_name: Mapped[str] = mapped_column(String(255))
    registration_url: Mapped[str | None] = mapped_column(String(1024))
    poster_file_id: Mapped[str | None] = mapped_column(String(512))
    # moderation state and timestamps
    status: Mapped[str] = mapped_column(
        String(32),
        default=EventStatus.PENDING.value,
        server_default=EventStatus.PENDING.value,
    )
    moderation_note: Mapped[str | None] = mapped_column(Text)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # event relationships
    creator: Mapped[User] = relationship(
        back_populates="created_events",
        foreign_keys=[creator_user_id],
    )
    parent_event: Mapped[Event | None] = relationship(
        remote_side=[id],
        back_populates="draft_updates",
    )
    draft_updates: Mapped[list[Event]] = relationship(
        back_populates="parent_event",
        cascade="all, delete-orphan",
    )
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_user_id])
    club: Mapped[Club | None] = relationship(back_populates="events")
    category: Mapped[EventCategory] = relationship(back_populates="events")
    detail_messages: Mapped[list[EventDetailMessage]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    favorites: Mapped[list[Favorite]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    moderation_logs: Mapped[list[ModerationLog]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    analytics: Mapped[list[EventAnalytics]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    ratings: Mapped[list[Rating]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )


# stores telegram messages for event detail posts
class EventDetailMessage(TimestampMixin, Base):
    __tablename__ = "event_detail_messages"

    # one detail message per event and chat
    __table_args__ = (
        UniqueConstraint(
            "event_id", "chat_id", name="uq_event_detail_messages_event_id_chat_id"
        ),
        Index("ix_event_detail_messages_chat_message", "chat_id", "message_id"),
    )

    # message identity and link data
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    message_id: Mapped[int] = mapped_column(BigInteger)
    message_link: Mapped[str | None] = mapped_column(String(1024))

    # links detail messages back to event and chat
    event: Mapped[Event] = relationship(back_populates="detail_messages")
    chat: Mapped[Chat] = relationship(back_populates="event_detail_messages")
