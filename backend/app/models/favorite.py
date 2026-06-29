from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


# stores events favorited by users
class Favorite(Base):
    __tablename__ = "favorites"
    # prevent the same favorite twice
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_favorites_user_id_event_id"),
        Index("ix_favorites_user_created", "user_id", "created_at"),
        Index("ix_favorites_event_id", "event_id"),
    )

    # favorite identity fields
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # links favorite to user and event
    user: Mapped[User] = relationship(back_populates="favorites")
    event: Mapped[Event] = relationship(back_populates="favorites")
