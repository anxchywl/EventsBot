from __future__ import annotations

from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    init_data: str = Field(alias="initData")


class AuthResponse(BaseModel):
    token: str
    user: dict


class ReminderRequest(BaseModel):
    offset_minutes: int = Field(ge=1, le=143_999)


class EventListItem(BaseModel):
    token: str
    title: str
    date: str
    time: str
    location: str
    organizer: str
    category: str
    is_favorite: bool = False
    reminder_count: int = 0
    attendee_count: int = 0
    is_ended: bool = False
    is_archived: bool = False
    cover_url: str | None = None
    average_rating: float | None = None
    rating_count: int = 0
    friends_going: list[EventFriendGoing] = Field(default_factory=list)


class FriendAvatar(BaseModel):
    url: str | None = None
    initials: str


class FriendUserSummary(BaseModel):
    id: int
    nickname: str
    email: str | None = None
    avatar: FriendAvatar
    friend_count: int = 0
    mutual_friends_count: int = 0
    telegram_url: str | None = None
    relationship_status: str = "none"
    request_id: int | None = None


class EventFriendGoing(BaseModel):
    id: int
    nickname: str
    avatar: FriendAvatar
    friend_count: int = 0
    mutual_friends_count: int = 0
    telegram_url: str | None = None


class ReviewDetail(BaseModel):
    comment_id: int | None = None
    rating_id: int | None = None
    nickname: str
    avatar: FriendAvatar | None = None
    content: str | None = None
    score: int | None = None
    created_at: str
    is_own: bool = False
    can_delete: bool = False
    user_id: int | None = None


class EventDetail(BaseModel):
    token: str
    title: str
    description: str
    date: str
    time: str
    location: str
    map_url: str
    organizer: str
    category: str
    registration_url: str | None
    cover_url: str | None
    attendee_count: int
    share_url: str
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
    status: str


class ReminderGroup(BaseModel):
    date: str
    reminders: list[ReminderItem]


class EventFilterOption(BaseModel):
    value: str
    label: str


class EventFiltersResponse(BaseModel):
    categories: list[EventFilterOption]
    organizers: list[EventFilterOption]
    locations: list[EventFilterOption]


class ActionResponse(BaseModel):
    ok: bool = True
    message: str
    url: str | None = None


# auth & profile request schemas
class UserRegisterRequest(BaseModel):
    email: str
    password: str


class UserVerifyRequest(BaseModel):
    email: str
    code: str


class UserResendRequest(BaseModel):
    email: str


class UserLoginRequest(BaseModel):
    email: str
    password: str


class NicknameRequest(BaseModel):
    nickname: str


class ForgotPasswordRequestBody(BaseModel):
    email: str


class ForgotPasswordVerifyBody(BaseModel):
    email: str
    code: str


class ForgotPasswordResetBody(BaseModel):
    email: str
    code: str
    new_password: str


class ReviewSubmitRequest(BaseModel):
    score: int | None = Field(default=None, ge=1, le=5)
    content: str | None = Field(default=None)


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
    blocked_reason: str | None = None
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
    user_id: int | None = None
    invite_token: str | None = None


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
