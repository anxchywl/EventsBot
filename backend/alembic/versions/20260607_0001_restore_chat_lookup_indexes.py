"""restore chat lookup indexes

Revision ID: 20260607_0001
Revises: 2eaf66765e24
Create Date: 2026-06-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260607_0001"
down_revision: Union[str, Sequence[str], None] = "2eaf66765e24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chats_bot_id_active "
        "ON chats (bot_id, is_active)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chats_status_activity "
        "ON chats (is_active, last_activity_at)"
    )


def downgrade() -> None:
    op.drop_index("ix_chats_status_activity", table_name="chats")
    op.drop_index("ix_chats_bot_id_active", table_name="chats")
