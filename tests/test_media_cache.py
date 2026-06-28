from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.friends import avatar_payload
from app.web.cache import TTLCache
from app.web.serializers import event_cover_url


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
