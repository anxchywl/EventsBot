"""add mini app friends system

Revision ID: 20260606_0001
Revises: 20260604_0001
Create Date: 2026-06-06 00:01:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260606_0001"
down_revision: Union[str, Sequence[str], None] = "20260604_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "friendships",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("friend_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("user_id < friend_user_id", name=op.f("ck_friendships_friendship_order")),
        sa.ForeignKeyConstraint(["friend_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "friend_user_id", name="uq_friendships_pair"),
    )
    op.create_index("ix_friendships_user_id", "friendships", ["user_id"])
    op.create_index("ix_friendships_friend_user_id", "friendships", ["friend_user_id"])

    op.create_table(
        "friend_invites",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('active', 'revoked', 'expired')", name=op.f("ck_friend_invites_friend_invite_status")),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_friend_invites_token_hash"),
    )
    op.create_index("ix_friend_invites_owner_status", "friend_invites", ["owner_id", "status", "expires_at"])

    op.create_table(
        "friend_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("requester_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_id", sa.BigInteger(), nullable=False),
        sa.Column("invite_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("requester_id <> recipient_id", name=op.f("ck_friend_requests_friend_request_not_self")),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'cancelled', 'expired')", name=op.f("ck_friend_requests_friend_request_status")),
        sa.ForeignKeyConstraint(["invite_id"], ["friend_invites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_friend_requests_pending_pair",
        "friend_requests",
        ["requester_id", "recipient_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_friend_requests_recipient_status", "friend_requests", ["recipient_id", "status", "created_at"])
    op.create_index("ix_friend_requests_requester_status", "friend_requests", ["requester_id", "status", "created_at"])

    op.create_table(
        "privacy_settings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("show_favorites_to_friends", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("show_profile_to_friends", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("allow_friend_requests", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_privacy_settings_user_id"),
    )

    op.create_index("ix_users_verified_nickname_search", "users", ["is_verified", "nickname"])
    op.create_index("ix_users_verified_email_search", "users", ["is_verified", "email"])


def downgrade() -> None:
    op.drop_index("ix_users_verified_email_search", table_name="users")
    op.drop_index("ix_users_verified_nickname_search", table_name="users")
    op.drop_table("privacy_settings")
    op.drop_index("ix_friend_requests_requester_status", table_name="friend_requests")
    op.drop_index("ix_friend_requests_recipient_status", table_name="friend_requests")
    op.drop_index("uq_friend_requests_pending_pair", table_name="friend_requests")
    op.drop_table("friend_requests")
    op.drop_index("ix_friend_invites_owner_status", table_name="friend_invites")
    op.drop_table("friend_invites")
    op.drop_index("ix_friendships_friend_user_id", table_name="friendships")
    op.drop_index("ix_friendships_user_id", table_name="friendships")
    op.drop_table("friendships")
