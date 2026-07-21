from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest

from app.models.enums import EventStatus
from app.services.friends import avatar_payload
from app.web.cache import TTLCache
from app.web.serializers import (
    get_reminder_counts,
    is_event_archived,
    is_event_ended,
    palette_key,
    user_reminder_details,
    user_reminder_offsets,
)
from app.web.serializers import event_cover_url


class FakeSession:
    def __init__(self, rows=None, scalars=None):
        self.rows = rows or []
        self.scalars = scalars or []
        self.executed = False

    async def execute(self, _stmt):
        self.executed = True
        return FakeResult(rows=self.rows, scalars=self.scalars)


class FakeResult:
    def __init__(self, rows=None, scalars=None):
        self.rows = rows or []
        self.scalar_values = scalars or []

    def all(self):
        return self.rows

    def scalars(self):
        return FakeScalars(self.scalar_values)


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


def test_ttl_cache_evicts_oldest_when_max_items_reached():
    cache = TTLCache(ttl_seconds=60, max_items=2)

    cache.set("first", 1)
    cache.set("second", 2)
    cache.set("third", 3)

    assert cache.get("first") is None
    assert cache.get("second") == 2
    assert cache.get("third") == 3


def test_event_cover_url_is_versioned_by_poster_file_id():
    event = SimpleNamespace(
        public_token="event-token", poster_file_id="telegram/file:id"
    )

    assert (
        event_cover_url(event) == "/api/events/event-token/cover?v=telegram%2Ffile%3Aid"
    )


def test_avatar_payload_versions_telegram_fallback_url():
    user = SimpleNamespace(
        telegram_id=12345,
        photo_url=None,
        photo_updated_at=datetime(2026, 6, 7, 12, 30, tzinfo=UTC),
        nickname="Ada Lovelace",
        email=None,
        username=None,
    )

    payload = avatar_payload(user)

    assert (
        payload["url"] == "/api/events/avatar/12345?v=2026-06-07T12%3A30%3A00%2B00%3A00"
    )
    assert payload["initials"] == "AL"


def test_event_cover_url_returns_none_without_poster():
    event = SimpleNamespace(public_token="event-token", poster_file_id=None)

    assert event_cover_url(event) is None


def test_event_cover_url_returns_external_https_url_directly():
    event = SimpleNamespace(
        public_token="event-token",
        poster_file_id="https://nu.edu.kz/images/event.jpg",
    )

    assert event_cover_url(event) == "https://nu.edu.kz/images/event.jpg"


def test_palette_key_is_stable_for_same_token():
    assert palette_key("event-token") == palette_key("event-token")


def test_event_archived_only_uses_manual_status():
    archived = SimpleNamespace(status=EventStatus.ARCHIVED.value)
    cancelled = SimpleNamespace(status=EventStatus.CANCELLED.value)

    assert is_event_archived(archived) is True
    assert is_event_archived(cancelled) is False


def test_future_event_is_not_ended():
    event = SimpleNamespace(
        event_date=date(2099, 1, 1),
        event_time=time(18, 30),
        timezone="Asia/Almaty",
    )

    assert is_event_ended(event) is False


def test_event_ended_falls_back_to_utc_for_invalid_timezone():
    event = SimpleNamespace(
        event_date=date(2020, 1, 1),
        event_time=time(18, 30),
        timezone="not-a-timezone",
    )

    assert is_event_ended(event) is True


@pytest.mark.anyio
async def test_get_reminder_counts_skips_empty_event_ids():
    session = FakeSession()

    counts = await get_reminder_counts(session, None, [])

    assert counts == {}
    assert session.executed is False


@pytest.mark.anyio
async def test_get_reminder_counts_returns_database_counts():
    session = FakeSession(rows=[(10, 2), (20, 1)])

    counts = await get_reminder_counts(session, None, [10, 20, 30])

    assert counts == {10: 2, 20: 1}


@pytest.mark.anyio
async def test_user_reminder_offsets_returns_empty_without_user():
    session = FakeSession(scalars=[30])

    offsets = await user_reminder_offsets(session, None, 10)

    assert offsets == []
    assert session.executed is False


@pytest.mark.anyio
async def test_user_reminder_details_returns_ids_and_offsets():
    session = FakeSession(rows=[(1, 30), (2, 60)])
    user = SimpleNamespace(id=5)

    reminder_ids, offsets = await user_reminder_details(session, user, 10)

    assert reminder_ids == [1, 2]
    assert offsets == [30, 60]
