"""add event mini app filter indexes

Revision ID: 20260527_0001
Revises: 20260525_0002
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260527_0001"
down_revision = "20260525_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_events_status_organizer_date_time",
        "events",
        ["status", "organizer_name", "event_date", "event_time"],
    )
    op.create_index(
        "ix_events_status_category_date_time",
        "events",
        ["status", "category_id", "event_date", "event_time"],
    )
    op.create_index(
        "ix_events_status_location_date_time",
        "events",
        ["status", "location", "event_date", "event_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_events_status_location_date_time", table_name="events")
    op.drop_index("ix_events_status_category_date_time", table_name="events")
    op.drop_index("ix_events_status_organizer_date_time", table_name="events")
