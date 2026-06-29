"""add_user_language

Revision ID: 20260601_0001
Revises: 20260528_0001
Create Date: 2026-06-01 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260601_0001"
down_revision = "20260528_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "language",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "language_selected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "language_selected")
    op.drop_column("users", "language")
