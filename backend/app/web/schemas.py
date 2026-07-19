from __future__ import annotations

import unicodedata
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import get_settings


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


_EMAIL_PATTERN = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


class UserRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=_EMAIL_PATTERN)
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
_CLIENT_REQUEST_ID_PATTERN = r"^[a-zA-Z0-9_-]{16,64}$"


def _normalize_single_line(value: object) -> object:
    if not isinstance(value, str):
        return value
    value = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("Control characters are not allowed.")
    return " ".join(value.split())


def _normalize_required_multiline(value: object) -> object:
    if not isinstance(value, str):
        return value
    value = (
        unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    )
    if any(
        unicodedata.category(char) == "Cc" and char not in {"\n", "\t"}
        for char in value
    ):
        raise ValueError("Control characters are not allowed.")
    return value.strip()


def _normalize_optional_multiline(value: object) -> object:
    if value is None:
        return None
    normalized = _normalize_required_multiline(value)
    return normalized or None


def _normalize_optional_single_line(value: object) -> object:
    if value is None:
        return None
    normalized = _normalize_single_line(value)
    return normalized or None


def _parse_event_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def validate_event_time_range(
    event_time: str,
    event_end_time: str,
) -> tuple[time, time]:
    start_time = _parse_event_time(event_time)
    end_time = _parse_event_time(event_end_time)
    if end_time <= start_time:
        raise ValueError("End time must be strictly later than start time.")
    return start_time, end_time


def validate_event_schedule(
    event_date: date,
    event_time: str,
    event_end_time: str,
) -> tuple[time, time]:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.app_timezone))
    start_time, end_time = validate_event_time_range(event_time, event_end_time)

    if event_date < now.date():
        raise ValueError("Event date cannot be in the past.")

    current_minute = now.time().replace(second=0, microsecond=0)
    if event_date == now.date() and start_time <= current_minute:
        raise ValueError("Event start time has already passed today.")

    return start_time, end_time


# registration_url is stored and rendered as a tappable link by every client;
# reject anything that is not a plain http(s) URL so a javascript:/data:/file:
# scheme can never reach a client that launches it. The bot enforces the same
# rule on its own submission path — this closes the equivalent Flutter path.
def _validate_registration_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if any(char.isspace() for char in value):
        raise ValueError("Registration link must be a full http(s):// URL.")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Registration link must be a full http(s):// URL.")
    return value


class FlutterRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=_EMAIL_PATTERN)
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
    submitted_at: str


class FlutterEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    event_date: date
    event_time: str = Field(pattern=_TIME_PATTERN)
    event_end_time: str = Field(pattern=_TIME_PATTERN)
    location: str = Field(min_length=1, max_length=100)
    category_id: int = Field(ge=1)
    organizer_name: str = Field(min_length=1, max_length=100)
    it_equipment: str | None = Field(default=None, max_length=500)
    materials: str | None = Field(default=None, max_length=500)
    registration_url: str | None = Field(default=None, max_length=500)
    client_request_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=64,
        pattern=_CLIENT_REQUEST_ID_PATTERN,
    )
    # opaque token resolved server side
    cover_ref: str | None = Field(default=None, max_length=256)

    _normalize_single_line_fields = field_validator(
        "title", "location", "organizer_name", mode="before"
    )(_normalize_single_line)
    _normalize_description = field_validator("description", mode="before")(
        _normalize_required_multiline
    )
    _normalize_optional_multiline_fields = field_validator(
        "it_equipment", "materials", mode="before"
    )(_normalize_optional_multiline)
    _normalize_registration_link = field_validator("registration_url", mode="before")(
        _normalize_optional_single_line
    )
    _check_registration_url = field_validator("registration_url")(
        _validate_registration_url
    )

    @model_validator(mode="after")
    def validate_dates_and_times(self) -> FlutterEventCreate:
        validate_event_schedule(self.event_date, self.event_time, self.event_end_time)
        return self


class FlutterEventPatch(BaseModel):
    event_time: str | None = Field(default=None, pattern=_TIME_PATTERN)
    event_end_time: str | None = Field(default=None, pattern=_TIME_PATTERN)
    # remove_cover wins over cover_ref
    cover_ref: str | None = Field(default=None, max_length=256)
    remove_cover: bool = False

    @model_validator(mode="after")
    def validate_patch_times(self) -> FlutterEventPatch:
        if self.event_time and self.event_end_time:
            validate_event_time_range(self.event_time, self.event_end_time)
        return self


class FlutterEventStatusUpdate(BaseModel):
    status: Literal["approved", "rejected", "needs_changes"]
    comment: str | None = Field(default=None, max_length=500)

    _normalize_comment = field_validator("comment", mode="before")(
        _normalize_optional_multiline
    )

    @model_validator(mode="after")
    def validate_decision_comment(self) -> FlutterEventStatusUpdate:
        if self.status in {"rejected", "needs_changes"} and self.comment is None:
            raise ValueError("A comment is required for this decision.")
        return self


class FlutterEventCancel(BaseModel):
    comment: str | None = Field(default=None, max_length=500)

    _normalize_comment = field_validator("comment", mode="before")(
        _normalize_optional_multiline
    )


class FlutterEventResubmit(BaseModel):
    """Optional updated fields applied to an existing event on resubmission.

    Every field is optional: a creator may resubmit unchanged, or supply an
    updated payload (same shape as FlutterEventCreate). `note` is the creator's
    optional message stored on the moderation log.
    """

    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    event_date: date | None = None
    event_time: str | None = Field(default=None, pattern=_TIME_PATTERN)
    event_end_time: str | None = Field(default=None, pattern=_TIME_PATTERN)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    category_id: int | None = Field(default=None, ge=1)
    organizer_name: str | None = Field(default=None, min_length=1, max_length=100)
    it_equipment: str | None = Field(default=None, max_length=500)
    materials: str | None = Field(default=None, max_length=500)
    registration_url: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)
    client_request_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=64,
        pattern=_CLIENT_REQUEST_ID_PATTERN,
    )
    # remove_cover wins over cover_ref
    cover_ref: str | None = Field(default=None, max_length=256)
    remove_cover: bool = False

    _normalize_single_line_fields = field_validator(
        "title", "location", "organizer_name", mode="before"
    )(_normalize_optional_single_line)
    _normalize_description = field_validator("description", mode="before")(
        _normalize_optional_multiline
    )
    _normalize_optional_multiline_fields = field_validator(
        "it_equipment", "materials", "note", mode="before"
    )(_normalize_optional_multiline)
    _normalize_registration_link = field_validator("registration_url", mode="before")(
        _normalize_optional_single_line
    )
    _check_registration_url = field_validator("registration_url")(
        _validate_registration_url
    )

    @model_validator(mode="after")
    def validate_dates_and_times(self) -> FlutterEventResubmit:
        for field_name in (
            "title",
            "description",
            "location",
            "organizer_name",
        ):
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"{field_name} cannot be empty.")

        settings = get_settings()
        tz = ZoneInfo(settings.app_timezone)
        now = datetime.now(tz)
        today = now.date()

        if self.event_date is not None and self.event_date < today:
            raise ValueError("Event date cannot be in the past.")

        start_time = end_time = None
        if self.event_time is not None:
            start_time = _parse_event_time(self.event_time)
        if self.event_end_time is not None:
            end_time = _parse_event_time(self.event_end_time)

        if (
            self.event_date is not None
            and self.event_date == today
            and start_time is not None
            and start_time <= now.time().replace(second=0, microsecond=0)
        ):
            raise ValueError("Event start time has already passed today.")

        if start_time is not None and end_time is not None and end_time <= start_time:
            raise ValueError("End time must be strictly later than start time.")

        return self


# ── Coordinator analytics dashboard ──────────────────────────────────────────


class FlutterAnalyticsSummary(BaseModel):
    """Keyed summary-card metrics.

    A map (not fixed fields) so a new card can be added later without a breaking
    change to the response shape; unknown/absent keys degrade gracefully client
    side. Values may be null when a metric has no data yet (e.g. no ratings).
    """

    metrics: dict[str, float | int | None]


class FlutterAnalyticsRankedEvent(BaseModel):
    event_id: int
    title: str
    value: float
    count: int | None = None


class FlutterLongestPending(BaseModel):
    event_id: int
    title: str
    waiting_seconds: float


class FlutterAnalyticsThresholdBucket(BaseModel):
    threshold_hours: int
    count: int


class FlutterAnalyticsModeration(BaseModel):
    approval_rate: float
    rejection_rate: float
    needs_changes_rate: float
    avg_time_to_first_decision_seconds: float | None = None
    avg_total_review_seconds: float | None = None
    avg_review_iterations: float | None = None
    queue_size: int
    longest_pending: FlutterLongestPending | None = None
    threshold_buckets: list[FlutterAnalyticsThresholdBucket]


class FlutterEngagementTotals(BaseModel):
    views: int
    register_clicks: int
    share_clicks: int
    reminder_creates: int
    favorites_added: int
    favorites_removed: int


class FlutterTrendPoint(BaseModel):
    date: str
    count: int


class FlutterAnalyticsEngagement(BaseModel):
    totals: FlutterEngagementTotals
    views_over_time: list[FlutterTrendPoint]


class FlutterAnalyticsCategory(BaseModel):
    category_id: int
    category: str
    event_count: int
    views: int
    registration_clicks: int
    average_rating: float | None = None
    approval_rate: float


class FlutterAnalyticsOrganizer(BaseModel):
    organizer: str
    events_created: int
    approval_rate: float
    rejection_rate: float
    average_rating: float | None = None
    views: int
    registration_clicks: int
    favorites: int


class FlutterAnalyticsEventOption(BaseModel):
    id: int
    title: str
    category: str
    event_date: str
    status: str


class FlutterAnalyticsRatings(BaseModel):
    average: float | None = None
    distribution: dict[str, int]
    total_reviews: int
    events_with_zero_reviews: int
    top_rated: list[FlutterAnalyticsRankedEvent]
    lowest_rated: list[FlutterAnalyticsRankedEvent]


class FlutterModerationLogEntry(BaseModel):
    action: str
    actor_name: str | None = None
    comment: str | None = None
    created_at: str


class FlutterEventModerationDetail(BaseModel):
    current_status: str
    submitted_at: str | None = None
    first_reviewed_at: str | None = None
    approved_at: str | None = None
    rejected_at: str | None = None
    total_review_seconds: float | None = None
    review_iterations: int
    needs_changes_count: int
    resubmission_count: int
    latest_moderator: str | None = None
    latest_comment: str | None = None
    last_status_update: str | None = None
    creator_resubmitted: bool
    history: list[FlutterModerationLogEntry] = []


class FlutterEventReview(BaseModel):
    rating_id: int
    user_id: int
    display_name: str
    username: str | None = None
    photo_url: str | None = None
    score: int
    content: str | None = None
    created_at: str
