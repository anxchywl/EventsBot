# add event submission idempotency key

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260719_0001"
down_revision: Union[str, Sequence[str], None] = "20260707_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("client_request_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column(
            "client_request_fingerprint",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_events_client_request_id",
        "events",
        ["client_request_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_events_client_request_id", table_name="events")
    op.drop_column("events", "client_request_fingerprint")
    op.drop_column("events", "client_request_id")
