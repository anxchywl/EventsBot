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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import ReminderStatus

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class Reminder(TimestampMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "event_id",
            "reminder_type",
            name="uq_reminders_user_id_event_id_reminder_type",
        ),
        CheckConstraint(
            "reminder_type IN ('one_day', 'one_hour')", name="reminder_type"
        ),
        CheckConstraint(
            "status IN ('scheduled', 'sent', 'cancelled', 'failed')", name="status"
        ),
        Index("ix_reminders_status_remind_at", "status", "remind_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reminder_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(32),
        default=ReminderStatus.SCHEDULED.value,
        server_default=ReminderStatus.SCHEDULED.value,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="reminders")
    event: Mapped[Event] = relationship(back_populates="reminders")
