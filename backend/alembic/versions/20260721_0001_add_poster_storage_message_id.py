# add poster storage message id to events

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260721_0001"
down_revision: Union[str, Sequence[str], None] = "20260719_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("poster_storage_message_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "poster_storage_message_id")
