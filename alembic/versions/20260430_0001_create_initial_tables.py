"""create initial tables

Revision ID: 20260430_0001
Revises:
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260430_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# creates the initial database schema
def upgrade() -> None:
    # stores telegram users
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column(
            "is_bot", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_moderator",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_users_telegram_id")),
    )
    op.create_index(
        op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=False
    )

    # stores event categories
    op.create_table(
        "event_categories",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_categories")),
        sa.UniqueConstraint("name", name=op.f("uq_event_categories_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_event_categories_slug")),
    )
    # inserts default event categories
    event_categories = sa.table(
        "event_categories",
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        event_categories,
        [
            {"name": "Computer Science", "slug": "computer-science", "sort_order": 10},
            {"name": "Business", "slug": "business", "sort_order": 20},
            {"name": "Startups", "slug": "startups", "sort_order": 30},
            {"name": "Engineering", "slug": "engineering", "sort_order": 40},
            {"name": "Design", "slug": "design", "sort_order": 50},
            {"name": "Career", "slug": "career", "sort_order": 60},
            {"name": "Hackathons", "slug": "hackathons", "sort_order": 70},
            {"name": "Workshops", "slug": "workshops", "sort_order": 80},
            {"name": "Sport", "slug": "sport", "sort_order": 90},
            {"name": "Volunteering", "slug": "volunteering", "sort_order": 100},
            {"name": "Entertainment", "slug": "entertainment", "sort_order": 110},
            {"name": "Club Events", "slug": "club-events", "sort_order": 120},
        ],
    )

    # stores student clubs
    op.create_table(
        "clubs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("contact_link", sa.String(length=512), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_clubs_owner_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clubs")),
        sa.UniqueConstraint("name", name=op.f("uq_clubs_name")),
    )

    # stores telegram chats
    op.create_table(
        "chats",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("chat_type", sa.String(length=32), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chat_type IN ('private', 'group', 'supergroup', 'channel')",
            name=op.f("ck_chats_chat_type"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_chats_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chats")),
        sa.UniqueConstraint("telegram_chat_id", name=op.f("uq_chats_telegram_chat_id")),
    )
    op.create_index(
        op.f("ix_chats_telegram_chat_id"), "chats", ["telegram_chat_id"], unique=False
    )

    # stores submitted events
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("creator_user_id", sa.BigInteger(), nullable=False),
        sa.Column("club_id", sa.BigInteger(), nullable=True),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Asia/Almaty'"),
            nullable=False,
        ),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("organizer_name", sa.String(length=255), nullable=False),
        sa.Column("registration_url", sa.String(length=1024), nullable=True),
        sa.Column("poster_file_id", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'needs_changes', 'cancelled')",
            name=op.f("ck_events_status"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name=op.f("fk_events_approved_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["event_categories.id"],
            name=op.f("fk_events_category_id_event_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["club_id"],
            ["clubs.id"],
            name=op.f("fk_events_club_id_clubs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["creator_user_id"],
            ["users.id"],
            name=op.f("fk_events_creator_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(
        "ix_events_category_date_time",
        "events",
        ["category_id", "event_date", "event_time"],
        unique=False,
    )
    op.create_index(
        "ix_events_status_date_time",
        "events",
        ["status", "event_date", "event_time"],
        unique=False,
    )

    # stores category settings per chat
    op.create_table(
        "chat_category_settings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["event_categories.id"],
            name=op.f("fk_chat_category_settings_category_id_event_categories"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_chat_category_settings_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_category_settings")),
        sa.UniqueConstraint(
            "chat_id",
            "category_id",
            name=op.f("uq_chat_category_settings_chat_id_category_id"),
        ),
    )

    # stores dashboard message ids
    op.create_table(
        "dashboard_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("last_rendered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_render_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_dashboard_messages_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dashboard_messages")),
        sa.UniqueConstraint("chat_id", name=op.f("uq_dashboard_messages_chat_id")),
    )

    # stores published event message ids
    op.create_table(
        "event_detail_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("message_link", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_event_detail_messages_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_detail_messages_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_detail_messages")),
        sa.UniqueConstraint(
            "event_id",
            "chat_id",
            name=op.f("uq_event_detail_messages_event_id_chat_id"),
        ),
    )
    op.create_index(
        "ix_event_detail_messages_chat_message",
        "event_detail_messages",
        ["chat_id", "message_id"],
        unique=False,
    )

    # stores user favorites
    op.create_table(
        "favorites",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_favorites_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_favorites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_favorites")),
        sa.UniqueConstraint(
            "user_id", "event_id", name=op.f("uq_favorites_user_id_event_id")
        ),
    )

    # stores moderation history
    op.create_table(
        "moderation_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("moderator_user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('submitted', 'approved', 'rejected', 'edited', 'needs_changes', 'cancelled')",
            name=op.f("ck_moderation_logs_action"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_moderation_logs_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["moderator_user_id"],
            ["users.id"],
            name=op.f("fk_moderation_logs_moderator_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moderation_logs")),
    )
    op.create_index(
        "ix_moderation_logs_event_created",
        "moderation_logs",
        ["event_id", "created_at"],
        unique=False,
    )

    # stores scheduled reminders
    op.create_table(
        "reminders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminder_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'scheduled'"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reminder_type IN ('one_day', 'one_hour')",
            name=op.f("ck_reminders_reminder_type"),
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'sent', 'cancelled', 'failed')",
            name=op.f("ck_reminders_status"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_reminders_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reminders_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
        sa.UniqueConstraint(
            "user_id",
            "event_id",
            "reminder_type",
            name=op.f("uq_reminders_user_id_event_id_reminder_type"),
        ),
    )
    op.create_index(
        "ix_reminders_status_remind_at",
        "reminders",
        ["status", "remind_at"],
        unique=False,
    )


# drops the initial database schema
def downgrade() -> None:
    op.drop_index("ix_reminders_status_remind_at", table_name="reminders")
    op.drop_table("reminders")
    op.drop_index("ix_moderation_logs_event_created", table_name="moderation_logs")
    op.drop_table("moderation_logs")
    op.drop_table("favorites")
    op.drop_index(
        "ix_event_detail_messages_chat_message", table_name="event_detail_messages"
    )
    op.drop_table("event_detail_messages")
    op.drop_table("dashboard_messages")
    op.drop_table("chat_category_settings")
    op.drop_index("ix_events_status_date_time", table_name="events")
    op.drop_index("ix_events_category_date_time", table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_chats_telegram_chat_id"), table_name="chats")
    op.drop_table("chats")
    op.drop_table("clubs")
    op.drop_table("event_categories")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
