from app.models.analytics import EventAnalytics
from app.models.chat import Chat, ChatCategorySetting, DashboardMessage
from app.models.club import Club
from app.models.event import Event, EventCategory, EventDetailMessage
from app.models.event_sync import EventSyncJob
from app.models.favorite import Favorite
from app.models.friend import FriendInvite, FriendRequest, Friendship, PrivacySettings
from app.models.moderation import ModerationLog
from app.models.reminder import Reminder
from app.models.user import User
from app.models.rating import Rating
from app.models.comment import Comment
from app.models.code import EmailVerificationCode
from app.models.password_reset import PasswordResetCode
from app.models.audit import AuditLog, UserActivityLog

# exports models for imports and migrations
__all__ = (
    "AuditLog",
    "UserActivityLog",
    "Chat",
    "ChatCategorySetting",
    "Club",
    "Comment",
    "DashboardMessage",
    "EmailVerificationCode",
    "PasswordResetCode",
    "Event",
    "EventAnalytics",
    "EventCategory",
    "EventDetailMessage",
    "EventSyncJob",
    "Favorite",
    "FriendInvite",
    "FriendRequest",
    "Friendship",
    "ModerationLog",
    "PrivacySettings",
    "Rating",
    "Reminder",
    "User",
)
