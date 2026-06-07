from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


# store hashed password reset codes and retry state
class PasswordResetCode(Base):
    """Stores hashed password reset codes for NU email accounts.

    Only one active code is kept per user at a time — old codes are
    deleted before a new one is inserted.  The plain code is never
    persisted; only its SHA-256 hex digest is stored.
    """

    __tablename__ = "password_reset_codes"
    __table_args__ = (
        Index("ix_password_reset_codes_user_id", "user_id"),
        Index("ix_password_reset_codes_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # store only a hash of the emailed code
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # lock the code after repeated wrong guesses
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # expire stale reset attempts
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # throttle resend requests per user
    resend_available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # prevent the same code from resetting twice
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="password_reset_codes")
