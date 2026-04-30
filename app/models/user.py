from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.club import Club
    from app.models.event import Event
    from app.models.favorite import Favorite
    from app.models.moderation import ModerationLog
    from app.models.reminder import Reminder


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(16))
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_moderator: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

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
