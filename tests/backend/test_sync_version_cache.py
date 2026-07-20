import os
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from app.web.routers import events as events_module  # noqa: E402


class SyncVersionCacheTest(unittest.IsolatedAsyncioTestCase):
    """The hot /sync-version endpoint must collapse the per-client aggregate to
    one query per short TTL rather than one query per polling client."""

    async def asyncSetUp(self) -> None:
        events_module._sync_version_cache.clear()
        self.calls = 0

        async def fake_latest(session) -> dict:
            self.calls += 1
            return {"version": self.calls, "completed_at": None}

        self._original = events_module.latest_completed_sync_version
        events_module.latest_completed_sync_version = fake_latest

    async def asyncTearDown(self) -> None:
        events_module.latest_completed_sync_version = self._original
        events_module._sync_version_cache.clear()

    async def test_second_call_within_ttl_is_served_from_cache(self) -> None:
        first = await events_module.event_sync_version(session=None)
        second = await events_module.event_sync_version(session=None)
        self.assertEqual(first, second)
        # the underlying aggregate ran exactly once
        self.assertEqual(self.calls, 1)

    async def test_expired_or_cleared_cache_recomputes(self) -> None:
        await events_module.event_sync_version(session=None)
        events_module._sync_version_cache.clear()
        await events_module.event_sync_version(session=None)
        self.assertEqual(self.calls, 2)


if __name__ == "__main__":
    unittest.main()
