from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ModerationAction

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class ModerationLog(Base):
    __tablename__ = "moderation_logs"
    __table_args__ = (
        CheckConstraint(
            "action IN ('submitted', 'approved', 'rejected', 'edited', 'needs_changes', 'cancelled')",
            name="action",
        ),
        Index("ix_moderation_logs_event_created", "event_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    moderator_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(
        String(32),
        default=ModerationAction.SUBMITTED.value,
    )
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped[Event] = relationship(back_populates="moderation_logs")
    moderator: Mapped[User | None] = relationship(back_populates="moderation_logs")
