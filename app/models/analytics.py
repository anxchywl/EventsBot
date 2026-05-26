from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


# stores user interactions with event pages
class EventAnalytics(TimestampMixin, Base):
    __tablename__ = "event_analytics"
    __table_args__ = (
        Index("ix_event_analytics_event_action_created", "event_id", "action", "created_at"),
        Index("ix_event_analytics_user_action_created", "user_id", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(32))
    source: Mapped[str | None] = mapped_column(String(64))
    chat_id: Mapped[int | None] = mapped_column(BigInteger)

    event: Mapped[Event] = relationship(back_populates="analytics")
    user: Mapped[User | None] = relationship(back_populates="event_analytics")
