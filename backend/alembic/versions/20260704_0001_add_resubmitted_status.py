"""add resubmitted event status and moderation action

Revision ID: 20260704_0001
Revises: 62e973abeaa4
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260704_0001"
down_revision: Union[str, Sequence[str], None] = "62e973abeaa4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_events_status"), "events", type_="check")
    op.create_check_constraint(
        op.f("ck_events_status"),
        "events",
        "status IN ('pending', 'approved', 'archived', 'rejected', 'needs_changes', 'resubmitted', 'cancelled')",
    )

    op.drop_constraint(op.f("ck_moderation_logs_action"), "moderation_logs", type_="check")
    op.create_check_constraint(
        op.f("ck_moderation_logs_action"),
        "moderation_logs",
        "action IN ('submitted', 'approved', 'archived', 'restored', 'rejected', 'edited', 'needs_changes', 'resubmitted', 'cancelled')",
    )


def downgrade() -> None:
    # revert any resubmitted rows to the prior states so the tighter
    # constraints can be re-applied without violation
    op.execute("UPDATE events SET status = 'needs_changes' WHERE status = 'resubmitted'")
    op.execute("UPDATE moderation_logs SET action = 'needs_changes' WHERE action = 'resubmitted'")

    op.drop_constraint(op.f("ck_moderation_logs_action"), "moderation_logs", type_="check")
    op.create_check_constraint(
        op.f("ck_moderation_logs_action"),
        "moderation_logs",
        "action IN ('submitted', 'approved', 'archived', 'restored', 'rejected', 'edited', 'needs_changes', 'cancelled')",
    )

    op.drop_constraint(op.f("ck_events_status"), "events", type_="check")
    op.create_check_constraint(
        op.f("ck_events_status"),
        "events",
        "status IN ('pending', 'approved', 'archived', 'rejected', 'needs_changes', 'cancelled')",
    )
