import os
import unittest
from datetime import date, time
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

import asyncio  # noqa: E402

from app.models.enums import EventStatus  # noqa: E402
from app.web.serializers import (  # noqa: E402
    PALETTE_KEYS,
    event_cover_url,
    is_event_archived,
    is_event_ended,
    palette_key,
    rating_summaries,
)


def _run(coro):
    return asyncio.run(coro)


class CoverUrlTest(unittest.TestCase):
    def test_no_poster_returns_none(self):
        event = SimpleNamespace(public_token="tok", poster_file_id=None)
        self.assertIsNone(event_cover_url(event))

    def test_cover_url_is_versioned_by_file_id(self):
        # the ?v=<file_id> query busts a stale cached image the moment the cover
        # changes, so a replaced poster is never served from an old cache entry
        event = SimpleNamespace(public_token="tok-1", poster_file_id="fid-abc")
        url = event_cover_url(event)
        self.assertTrue(url.startswith("/api/events/tok-1/cover?"))
        self.assertIn("v=fid-abc", url)

    def test_cover_url_changes_when_file_id_changes(self):
        old = event_cover_url(SimpleNamespace(public_token="t", poster_file_id="a"))
        new = event_cover_url(SimpleNamespace(public_token="t", poster_file_id="b"))
        self.assertNotEqual(old, new)


class EndedAndArchivedTest(unittest.TestCase):
    def _event(self, event_date, status=EventStatus.APPROVED.value):
        return SimpleNamespace(
            event_date=event_date,
            event_time=time(12, 0),
            timezone="UTC",
            status=status,
        )

    def test_past_event_is_ended(self):
        self.assertTrue(is_event_ended(self._event(date(2000, 1, 1))))

    def test_far_future_event_is_not_ended(self):
        self.assertFalse(is_event_ended(self._event(date(2099, 1, 1))))

    def test_bad_timezone_falls_back_to_utc(self):
        event = SimpleNamespace(
            event_date=date(2000, 1, 1),
            event_time=time(12, 0),
            timezone="Not/AZone",
            status=EventStatus.APPROVED.value,
        )
        self.assertTrue(is_event_ended(event))

    def test_archived_status_detected(self):
        self.assertTrue(
            is_event_archived(self._event(date(2099, 1, 1), EventStatus.ARCHIVED.value))
        )
        self.assertFalse(is_event_archived(self._event(date(2099, 1, 1))))


class PaletteKeyTest(unittest.TestCase):
    def test_palette_key_is_stable_and_known(self):
        key = palette_key("event_123")
        self.assertIn(key, PALETTE_KEYS)
        # deterministic for the same token so covers do not flicker between loads
        self.assertEqual(key, palette_key("event_123"))

    def test_different_tokens_can_map_to_different_palettes(self):
        keys = {palette_key(f"token-{i}") for i in range(20)}
        self.assertGreater(len(keys), 1)


class FakeAllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        return FakeAllResult(self._rows)


class RatingSummariesTest(unittest.TestCase):
    def test_empty_event_ids_short_circuits_without_query(self):
        session = FakeSession([])
        result = _run(rating_summaries(session, []))
        self.assertEqual(result, {})
        self.assertEqual(session.executed, 0)

    def test_summaries_default_to_none_zero_for_unrated_events(self):
        # event 2 has no rows -> stays (None, 0); event 1 is aggregated
        session = FakeSession([(1, 4.5, 2)])
        result = _run(rating_summaries(session, [1, 2]))
        self.assertEqual(result[1], (4.5, 2))
        self.assertEqual(result[2], (None, 0))

    def test_null_average_coerced_to_none(self):
        session = FakeSession([(1, None, 0)])
        result = _run(rating_summaries(session, [1]))
        self.assertEqual(result[1], (None, 0))


if __name__ == "__main__":
    unittest.main()
