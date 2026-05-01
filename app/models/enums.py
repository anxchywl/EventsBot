from enum import Enum


# tracks event review state
class EventStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    CANCELLED = "cancelled"


# defines reminder timing choices
class ReminderType(str, Enum):
    ONE_DAY = "one_day"
    ONE_HOUR = "one_hour"


# tracks reminder delivery state
class ReminderStatus(str, Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


# records moderation action types
class ModerationAction(str, Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    NEEDS_CHANGES = "needs_changes"
    CANCELLED = "cancelled"
