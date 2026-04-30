from enum import Enum


class EventStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    CANCELLED = "cancelled"


class ReminderType(str, Enum):
    ONE_DAY = "one_day"
    ONE_HOUR = "one_hour"


class ReminderStatus(str, Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ModerationAction(str, Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    NEEDS_CHANGES = "needs_changes"
    CANCELLED = "cancelled"
