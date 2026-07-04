from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AuthRequest(BaseModel):
    init_data: str = Field(alias="initData")


class AuthResponse(BaseModel):
    token: str
    user: dict


class ReminderRequest(BaseModel):
    offset_minutes: int = Field(ge=1, le=143_999)


class EventListItem(BaseModel):
    token: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=100)
    date: str = Field(min_length=1, max_length=32)
    time: str = Field(min_length=1, max_length=16)
    location: str = Field(min_length=1, max_length=100)
    organizer: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=64)
    is_favorite: bool = False
    reminder_count: int = 0
    attendee_count: int = 0
    is_ended: bool = False
    is_archived: bool = False
    cover_url: str | None = Field(default=None, max_length=2048)
    average_rating: float | None = None
    rating_count: int = 0
    friends_going: list[EventFriendGoing] = Field(default_factory=list)


class FriendAvatar(BaseModel):
    url: str | None = Field(default=None, max_length=2048)
    initials: str = Field(min_length=1, max_length=4)


class FriendUserSummary(BaseModel):
    id: int
    nickname: str = Field(min_length=1, max_length=64)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    avatar: FriendAvatar
    friend_count: int = 0
    mutual_friends_count: int = 0
    telegram_url: str | None = Field(default=None, max_length=255)
    relationship_status: str = "none"
    request_id: int | None = None


class EventFriendGoing(BaseModel):
    id: int
    nickname: str = Field(min_length=1, max_length=64)
    avatar: FriendAvatar
    friend_count: int = 0
    mutual_friends_count: int = 0
    telegram_url: str | None = Field(default=None, max_length=255)


class ReviewDetail(BaseModel):
    comment_id: int | None = None
    rating_id: int | None = None
    nickname: str = Field(min_length=1, max_length=64)
    avatar: FriendAvatar | None = None
    content: str | None = Field(default=None, max_length=1024)
    score: int | None = Field(default=None, ge=1, le=5)
    created_at: str
    is_own: bool = False
    can_delete: bool = False
    user_id: int | None = None


class FeedReviewDetail(BaseModel):
    event_token: str = Field(min_length=1, max_length=64)
    event_title: str = Field(min_length=1, max_length=100)
    nickname: str = Field(min_length=1, max_length=64)
    content: str | None = Field(default=None, max_length=1024)
    score: int | None = Field(default=None, ge=1, le=5)
    created_at: str
    user_id: int | None = None
    comment_id: int | None = None
    rating_id: int | None = None


class EventDetail(BaseModel):
    token: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=1000)
    date: str = Field(max_length=32)
    time: str = Field(max_length=16)
    location: str = Field(max_length=100)
    map_url: str = Field(max_length=2048)
    organizer: str = Field(max_length=100)
    category: str = Field(max_length=64)
    registration_url: str | None = Field(default=None, max_length=2048)
    cover_url: str | None = Field(default=None, max_length=2048)
    attendee_count: int
    share_url: str = Field(max_length=2048)
    is_favorite: bool = False
    reminder_offsets: list[int] = Field(default_factory=list)
    reminder_ids: list[int] = Field(default_factory=list)
    background_seed: str
    palette_key: str
    is_archived: bool = False
    related_events: list[EventListItem]
    average_rating: float | None = None
    rating_count: int = 0
    reviews: list[ReviewDetail] = Field(default_factory=list)
    friends_going: list[EventFriendGoing] = Field(default_factory=list)


class FavoriteResponse(BaseModel):
    is_favorite: bool


class RegisterResponse(BaseModel):
    attendee_count: int


class ReminderItem(BaseModel):
    id: int
    event: EventListItem
    offset_minutes: int
    remind_at: str
    status: str = Field(max_length=32)


class ReminderGroup(BaseModel):
    date: str
    reminders: list[ReminderItem]


class EventFilterOption(BaseModel):
    value: str = Field(max_length=128)
    label: str = Field(max_length=128)


class EventFiltersResponse(BaseModel):
    categories: list[EventFilterOption]
    organizers: list[EventFilterOption]
    locations: list[EventFilterOption]


class ActionResponse(BaseModel):
    ok: bool = True
    message: str = Field(max_length=512)
    url: str | None = Field(default=None, max_length=2048)


# auth & profile request schemas
class UserRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserVerifyRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=6, max_length=6)


class UserResendRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class UserLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class NicknameRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=64)


class ForgotPasswordRequestBody(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ForgotPasswordVerifyBody(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=6, max_length=6)


class ForgotPasswordResetBody(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=1, max_length=128)


class ReviewSubmitRequest(BaseModel):
    score: int | None = Field(default=None, ge=1, le=5)
    content: str | None = Field(default=None, max_length=1024)


class ProfileHistoryItem(BaseModel):
    event_token: str
    event_title: str
    comment_id: int | None = None
    rating_id: int | None = None
    score: int | None = None
    content: str | None = None
    created_at: str


class ProfileResponse(BaseModel):
    email: str
    nickname: str
    is_verified: bool
    is_blocked: bool = False
    blocked_reason: str | None = Field(default=None, max_length=512)
    history: list[ProfileHistoryItem] = Field(default_factory=list)


class PrivacySettingsResponse(BaseModel):
    show_favorites_to_friends: bool = True
    show_profile_to_friends: bool = True
    allow_friend_requests: bool = True


class PrivacySettingsUpdate(BaseModel):
    show_favorites_to_friends: bool | None = None
    show_profile_to_friends: bool | None = None
    allow_friend_requests: bool | None = None


class FriendRequestCreate(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    invite_token: str | None = Field(default=None, min_length=32, max_length=256)

    @model_validator(mode="after")
    def exactly_one_target(self):
        if bool(self.user_id) == bool(self.invite_token):
            raise ValueError("Provide exactly one friend request target.")
        return self


class FriendRequestItem(BaseModel):
    id: int
    status: str
    created_at: str
    expires_at: str
    user: FriendUserSummary


class FriendRequestsResponse(BaseModel):
    incoming: list[FriendRequestItem] = Field(default_factory=list)
    outgoing: list[FriendRequestItem] = Field(default_factory=list)


class FriendsListResponse(BaseModel):
    total: int
    friends: list[FriendUserSummary] = Field(default_factory=list)


class FriendSearchResponse(BaseModel):
    results: list[FriendUserSummary] = Field(default_factory=list)
    page: int
    limit: int
    has_more: bool = False


class FriendInviteResponse(BaseModel):
    id: int
    token: str
    url: str
    share_url: str | None = None
    expires_at: str


class FriendInviteLookupResponse(BaseModel):
    state: str
    inviter: FriendUserSummary | None = None


class FriendActionResponse(BaseModel):
    ok: bool = True
    message: str
    request_id: int | None = None


# flutter app: separate auth and event schemas for the mobile client

_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class FlutterRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=64)


class FlutterLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class FlutterAuthResponse(BaseModel):
    token: str
    user_id: int
    role: Literal["user", "admin"]
    first_name: str | None = None
    is_verified: bool


class FlutterCategoryItem(BaseModel):
    id: int
    name: str
    slug: str


class FlutterEventItem(BaseModel):
    id: int
    public_token: str
    title: str
    description: str
    event_date: str
    event_time: str
    event_end_time: str | None = None
    location: str
    category: str
    organizer_name: str
    status: str
    cover_url: str | None = None
    it_equipment: str | None = None
    materials: str | None = None
    registration_url: str | None = None
    moderation_note: str | None = None


class FlutterEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    event_date: date
    event_time: str = Field(pattern=_TIME_PATTERN)
    event_end_time: str = Field(pattern=_TIME_PATTERN)
    location: str = Field(min_length=1, max_length=255)
    category_id: int
    organizer_name: str = Field(min_length=1, max_length=255)
    it_equipment: str | None = None
    materials: str | None = None
    registration_url: str | None = Field(default=None, max_length=1024)


class FlutterEventPatch(BaseModel):
    event_end_time: str | None = Field(default=None, pattern=_TIME_PATTERN)


class FlutterEventStatusUpdate(BaseModel):
    status: Literal["approved", "rejected", "needs_changes", "cancelled"]
    comment: str | None = Field(default=None, max_length=500)
