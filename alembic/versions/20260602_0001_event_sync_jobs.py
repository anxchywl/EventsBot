"""add event sync jobs and archived event status

Revision ID: 20260602_0001
Revises: 20260601_0002
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260602_0001"
down_revision: Union[str, Sequence[str], None] = "20260601_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_events_status"), "events", type_="check")
    op.create_check_constraint(
        op.f("ck_events_status"),
        "events",
        "status IN ('pending', 'approved', 'archived', 'rejected', 'needs_changes', 'cancelled')",
    )
    op.add_column("events", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True))

    op.drop_constraint(op.f("ck_moderation_logs_action"), "moderation_logs", type_="check")
    op.create_check_constraint(
        op.f("ck_moderation_logs_action"),
        "moderation_logs",
        "action IN ('submitted', 'approved', 'archived', 'restored', 'rejected', 'edited', 'needs_changes', 'cancelled')",
    )

    op.create_table(
        "event_sync_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_sync_jobs")),
    )
    op.create_index(
        "ix_event_sync_jobs_status_created",
        "event_sync_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_event_sync_jobs_event_created",
        "event_sync_jobs",
        ["event_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_sync_jobs_event_created", table_name="event_sync_jobs")
    op.drop_index("ix_event_sync_jobs_status_created", table_name="event_sync_jobs")
    op.drop_table("event_sync_jobs")

    op.drop_constraint(op.f("ck_moderation_logs_action"), "moderation_logs", type_="check")
    op.create_check_constraint(
        op.f("ck_moderation_logs_action"),
        "moderation_logs",
        "action IN ('submitted', 'approved', 'rejected', 'edited', 'needs_changes', 'cancelled')",
    )

    op.drop_column("events", "restored_at")
    op.drop_column("events", "archived_at")
    op.drop_constraint(op.f("ck_events_status"), "events", type_="check")
    op.create_check_constraint(
        op.f("ck_events_status"),
        "events",
        "status IN ('pending', 'approved', 'rejected', 'needs_changes', 'cancelled')",
    )
