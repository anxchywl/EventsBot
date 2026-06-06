"""add connected group metadata

Revision ID: 20260602_0002
Revises: 20260602_0001
Create Date: 2026-06-02 00:00:01.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260602_0002"
down_revision: Union[str, Sequence[str], None] = "20260602_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("invite_link", sa.String(length=1024), nullable=True))
    op.add_column("chats", sa.Column("member_count", sa.BigInteger(), nullable=True))
    op.add_column("chats", sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chats", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chats", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE chats SET connected_at = created_at WHERE connected_at IS NULL")
    op.execute("UPDATE chats SET last_activity_at = updated_at WHERE last_activity_at IS NULL")
    op.create_index("ix_chats_status_activity", "chats", ["is_active", "last_activity_at"])


def downgrade() -> None:
    op.drop_index("ix_chats_status_activity", table_name="chats")
    op.drop_column("chats", "removed_at")
    op.drop_column("chats", "last_activity_at")
    op.drop_column("chats", "connected_at")
    op.drop_column("chats", "member_count")
    op.drop_column("chats", "invite_link")
