"""add_unique_constraints_to_code_tables

Revision ID: 20260623_0001
Revises: ad694c4c9406
Create Date: 2026-06-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260623_0001"
down_revision: Union[str, None] = "ad694c4c9406"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # deduplicate before adding the constraint so the migration is safe on dirty data
    op.execute("""
        DELETE FROM email_verification_codes
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id) id
            FROM email_verification_codes
            ORDER BY user_id, created_at DESC
        )
    """)
    op.create_unique_constraint(
        "uq_email_verification_codes_user_id",
        "email_verification_codes",
        ["user_id"],
    )

    op.execute("""
        DELETE FROM password_reset_codes
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id) id
            FROM password_reset_codes
            ORDER BY user_id, created_at DESC
        )
    """)
    op.create_unique_constraint(
        "uq_password_reset_codes_user_id",
        "password_reset_codes",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_password_reset_codes_user_id", "password_reset_codes", type_="unique"
    )
    op.drop_constraint(
        "uq_email_verification_codes_user_id", "email_verification_codes", type_="unique"
    )
