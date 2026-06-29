"""add event public tokens and analytics

Revision ID: 20260524_0001
Revises: 221e6b374de2
Create Date: 2026-05-24 00:00:00.000000
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "20260524_0001"
down_revision: Union[str, None] = "221e6b374de2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("public_token", sa.String(length=36), nullable=True))

    bind = op.get_bind()
    event_ids = bind.execute(sa.text("SELECT id FROM events")).scalars().all()
    for event_id in event_ids:
        bind.execute(
            sa.text("UPDATE events SET public_token = :token WHERE id = :event_id"),
            {"token": str(uuid4()), "event_id": event_id},
        )

    op.alter_column("events", "public_token", nullable=False)
    op.create_index("ix_events_public_token", "events", ["public_token"], unique=True)

    op.create_table(
        "event_analytics",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "action IN ('open', 'reminder_click', 'share_click')",
            name=op.f("ck_event_analytics_action"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_analytics_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_event_analytics_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_analytics")),
    )
    op.create_index(
        "ix_event_analytics_event_action_created",
        "event_analytics",
        ["event_id", "action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_analytics_event_action_created", table_name="event_analytics")
    op.drop_table("event_analytics")
    op.drop_index("ix_events_public_token", table_name="events")
    op.drop_column("events", "public_token")
