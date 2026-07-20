import asyncio
import contextlib
import os
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from app.web import realtime  # noqa: E402


def _reset() -> None:
    realtime._subscribers.clear()
    realtime._pending_analytics_metrics.clear()
    task = realtime._analytics_flush_task
    if task is not None and not task.done():
        task.cancel()
    realtime._analytics_flush_task = None


class ScheduleAnalyticsChangedNoLoopTest(unittest.TestCase):
    """Called from a sync context (no running loop) the hint is dropped without
    raising — the client poll still reconciles."""

    def setUp(self) -> None:
        _reset()

    def test_no_running_loop_clears_pending_and_does_not_raise(self) -> None:
        realtime.schedule_analytics_changed("open")
        self.assertEqual(realtime._pending_analytics_metrics, set())
        self.assertIsNone(realtime._analytics_flush_task)


class AnalyticsChangedDebounceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        _reset()
        self._original_debounce = realtime._ANALYTICS_DEBOUNCE_SECONDS
        realtime._ANALYTICS_DEBOUNCE_SECONDS = 0.02

    async def asyncTearDown(self) -> None:
        realtime._ANALYTICS_DEBOUNCE_SECONDS = self._original_debounce
        _reset()

    async def _subscribe(self):
        iterator = realtime.subscribe_miniapp_events(None)
        task = asyncio.ensure_future(iterator.__anext__())
        # let the generator body run far enough to register its queue
        await asyncio.sleep(0)
        return iterator, task

    async def test_bursts_coalesce_into_one_sorted_signal(self) -> None:
        iterator, first = await self._subscribe()
        try:
            # a burst of writes within the debounce window
            realtime.schedule_analytics_changed("open")
            realtime.schedule_analytics_changed("rating")
            realtime.schedule_analytics_changed("open")  # duplicate collapses

            message = await asyncio.wait_for(first, timeout=1.0)
            self.assertEqual(
                message,
                {"type": "analytics_changed", "metrics": ["open", "rating"]},
            )
            # exactly one flush: nothing else is queued
            second = asyncio.ensure_future(iterator.__anext__())
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(second), timeout=0.1)
            # let the cancellation settle before closing the generator
            second.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await second
        finally:
            await iterator.aclose()


class PublishBackpressureTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        _reset()

    async def asyncTearDown(self) -> None:
        _reset()

    async def test_full_queue_keeps_subscriber_and_newest_message(self) -> None:
        queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        subscriber = (None, queue)
        realtime._subscribers.add(subscriber)

        await realtime.publish_miniapp_event("e", {"n": 1})
        await realtime.publish_miniapp_event("e", {"n": 2})  # queue now full
        await realtime.publish_miniapp_event("e", {"n": 3})  # overflow

        # a slow client is NOT evicted (which used to leave it silently dead)
        self.assertIn(subscriber, realtime._subscribers)
        drained = [queue.get_nowait()["n"], queue.get_nowait()["n"]]
        # oldest (1) shed, newest (3) retained, stream stays live
        self.assertEqual(drained, [2, 3])


if __name__ == "__main__":
    unittest.main()
