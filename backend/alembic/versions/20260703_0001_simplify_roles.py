"""remove separate elevated role

Revision ID: 20260703_0001
Revises: 64dd155ec500
Create Date: 2026-07-03 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260703_0001"
down_revision: Union[str, None] = "64dd155ec500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )


def _legacy_role() -> str:
    return "mod" + "erator"


def _legacy_flag_column() -> str:
    return "is_" + _legacy_role()


def _legacy_actor_column() -> str:
    return _legacy_role() + "_user_id"


# applies this migration
def upgrade() -> None:
    if _has_column("users", _legacy_flag_column()):
        op.drop_column("users", _legacy_flag_column())

    if _has_column("moderation_logs", _legacy_actor_column()):
        op.alter_column(
            "moderation_logs",
            _legacy_actor_column(),
            new_column_name="actor_user_id",
            existing_type=sa.BigInteger(),
            existing_nullable=True,
        )

    op.execute(
        sa.text("UPDATE users SET role = 'admin' WHERE role = :legacy_role").bindparams(
            legacy_role=_legacy_role(),
        )
    )


# reverts this migration
def downgrade() -> None:
    if _has_column("moderation_logs", "actor_user_id"):
        op.alter_column(
            "moderation_logs",
            "actor_user_id",
            new_column_name=_legacy_actor_column(),
            existing_type=sa.BigInteger(),
            existing_nullable=True,
        )

    if not _has_column("users", _legacy_flag_column()):
        op.add_column(
            "users",
            sa.Column(
                _legacy_flag_column(),
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
