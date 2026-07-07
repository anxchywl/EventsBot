"""add events.creator_user_id lookup index

Revision ID: 20260707_0001
Revises: 20260706_0001
Create Date: 2026-07-07 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260707_0001"
down_revision: Union[str, Sequence[str], None] = "20260706_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Postgres does not auto-index foreign keys. list_my_events / get_user_events
# filter events by creator_user_id and order by created_at; without this index
# both run a sequential scan over the whole events table. Additive and safe.
def upgrade() -> None:
    op.create_index(
        "ix_events_creator_created",
        "events",
        ["creator_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_events_creator_created", table_name="events")
