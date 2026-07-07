"""add superapp_user_id identity bridge column

Revision ID: 20260706_0001
Revises: 20260704_0001
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260706_0001"
down_revision: Union[str, Sequence[str], None] = "20260704_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# additive, nullable column + unique index for the future superapp identity
# bridge. Safe to apply on a live DB: existing rows get NULL and are unaffected.
def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("superapp_user_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "uq_users_superapp_user_id",
        "users",
        ["superapp_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_superapp_user_id", table_name="users")
    op.drop_column("users", "superapp_user_id")
