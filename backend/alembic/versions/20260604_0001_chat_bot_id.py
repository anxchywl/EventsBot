"""add bot id to chats

Revision ID: 20260604_0001
Revises: 20260602_0001
Create Date: 2026-06-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260604_0001"
down_revision: Union[str, Sequence[str], None] = "20260602_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("bot_id", sa.BigInteger(), nullable=True))
    op.execute(
        """
        DELETE FROM event_analytics
        WHERE chat_id IN (
            SELECT telegram_chat_id
            FROM chats
            WHERE chat_type IN ('group', 'supergroup', 'channel')
        )
        """
    )
    op.execute(
        "DELETE FROM chats WHERE chat_type IN ('group', 'supergroup', 'channel')"
    )
    op.create_index("ix_chats_bot_id_active", "chats", ["bot_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_chats_bot_id_active", table_name="chats")
    op.drop_column("chats", "bot_id")
