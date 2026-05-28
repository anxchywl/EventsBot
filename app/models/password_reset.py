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

    # SHA-256 hex digest of the 6-digit code — never store the plain value.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # How many wrong guesses have been made against this code.
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # When the code stops being valid.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Earliest time the user is allowed to request a new code (60-second cooldown).
    resend_available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Set to the timestamp when the code was successfully consumed.
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
