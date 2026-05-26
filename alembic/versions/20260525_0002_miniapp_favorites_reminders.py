"""expand mini app favorites reminders and analytics

Revision ID: 20260525_0002
Revises: 20260524_0001
Create Date: 2026-05-25 00:02:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260525_0002"
down_revision: Union[str, None] = "20260524_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reminders", sa.Column("offset_minutes", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE reminders
        SET offset_minutes = CASE
            WHEN reminder_type = 'one_day' THEN 1440
            WHEN reminder_type = 'one_hour' THEN 60
            ELSE 60
        END
        WHERE offset_minutes IS NULL
        """
    )
    op.alter_column("reminders", "offset_minutes", nullable=False)

    op.execute(
        "ALTER TABLE reminders "
        "DROP CONSTRAINT IF EXISTS uq_reminders_user_id_event_id_reminder_type"
    )
    op.execute(
        "ALTER TABLE reminders "
        "DROP CONSTRAINT IF EXISTS ck_reminders_reminder_type"
    )
    op.execute(
        "ALTER TABLE reminders "
        "DROP CONSTRAINT IF EXISTS ck_reminders_status"
    )
    op.create_unique_constraint(
        "uq_reminders_user_id_event_id_offset_minutes",
        "reminders",
        ["user_id", "event_id", "offset_minutes"],
    )
    op.create_index(
        "ix_reminders_user_status_remind_at",
        "reminders",
        ["user_id", "status", "remind_at"],
    )

    op.create_index("ix_favorites_user_created", "favorites", ["user_id", "created_at"])
    op.create_index("ix_favorites_event_id", "favorites", ["event_id"])

    op.execute(
        "ALTER TABLE event_analytics "
        "DROP CONSTRAINT IF EXISTS ck_event_analytics_action"
    )
    op.create_index(
        "ix_event_analytics_user_action_created",
        "event_analytics",
        ["user_id", "action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_analytics_user_action_created", table_name="event_analytics")
    op.create_check_constraint(
        "ck_event_analytics_action",
        "event_analytics",
        "action IN ('open', 'reminder_click', 'share_click')",
    )

    op.drop_index("ix_favorites_event_id", table_name="favorites")
    op.drop_index("ix_favorites_user_created", table_name="favorites")

    op.drop_index("ix_reminders_user_status_remind_at", table_name="reminders")
    op.drop_constraint("uq_reminders_user_id_event_id_offset_minutes", "reminders", type_="unique")
    op.create_check_constraint(
        "ck_reminders_status",
        "reminders",
        "status IN ('scheduled', 'sent', 'cancelled', 'failed')",
    )
    op.create_check_constraint(
        "ck_reminders_reminder_type",
        "reminders",
        "reminder_type IN ('one_day', 'one_hour')",
    )
    op.create_unique_constraint(
        "uq_reminders_user_id_event_id_reminder_type",
        "reminders",
        ["user_id", "event_id", "reminder_type"],
    )
    op.drop_column("reminders", "offset_minutes")
