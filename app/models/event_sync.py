from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


# store queued event delivery jobs
class EventSyncJob(TimestampMixin, Base):
    __tablename__ = "event_sync_jobs"
    __table_args__ = (
        Index("ix_event_sync_jobs_status_created", "status", "created_at"),
        Index("ix_event_sync_jobs_event_created", "event_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int | None] = mapped_column(BigInteger)
    operation: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
    )
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
