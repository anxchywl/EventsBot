"""add verified_at to password_reset_codes and check constraint to event_analytics

Revision ID: 20260623_0002
Revises: 20260623_0001
Create Date: 2026-06-23
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260623_0002"
down_revision: Union[str, None] = "20260623_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # M-4: add verified_at to track that the verify step was completed before reset
    op.add_column(
        "password_reset_codes",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # DB-5: restrict event_analytics.action to known values
    op.create_check_constraint(
        "ck_event_analytics_action",
        "event_analytics",
        "action IN ('open','open_from_share','register_click','favorite_add','favorite_remove','share_click','reminder_create','reminder_remove','reminder_click')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_event_analytics_action", "event_analytics", type_="check")
    op.drop_column("password_reset_codes", "verified_at")
