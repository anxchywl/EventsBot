import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import app.services.event_sync as event_sync  # noqa: E402
from app.services.event_sync import (  # noqa: E402
    DELETE_LIKE_OPERATIONS,
    EventSyncWorker,
    _claim_next_job,
    _mark_job_failed,
    _snapshot_chat_ids,
    capture_event_snapshot,
    latest_completed_sync_version,
)


def _run(coro):
    return asyncio.run(coro)


class SnapshotChatIdsTest(unittest.TestCase):
    def test_collects_int_chat_ids_and_skips_missing(self):
        snapshot = {
            "detail_messages": [
                {"chat_id": 1, "message_id": 10},
                {"chat_id": "2", "message_id": 20},
                {"chat_id": None, "message_id": 30},
            ]
        }
        self.assertEqual(_snapshot_chat_ids(snapshot), {1, 2})

    def test_empty_snapshot_is_empty_set(self):
        self.assertEqual(_snapshot_chat_ids({}), set())


class FakeScalarOne:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class ClaimSession:
    def __init__(self, job):
        self._job = job
        self.flushed = 0

    async def execute(self, _stmt):
        return FakeScalarOne(self._job)

    async def flush(self):
        self.flushed += 1


class ClaimNextJobTest(unittest.TestCase):
    def test_claim_marks_processing_and_increments_attempts(self):
        job = SimpleNamespace(id=1, status="pending", attempts=0)
        session = ClaimSession(job)

        claimed = _run(_claim_next_job(session))

        self.assertIs(claimed, job)
        self.assertEqual(job.status, "processing")
        self.assertEqual(job.attempts, 1)
        self.assertEqual(session.flushed, 1)

    def test_no_pending_job_returns_none(self):
        session = ClaimSession(None)
        self.assertIsNone(_run(_claim_next_job(session)))
        # nothing to flush when there is no job to claim
        self.assertEqual(session.flushed, 0)


class MarkFailedTest(unittest.TestCase):
    def test_marks_failed_and_records_error(self):
        job = SimpleNamespace(id=7, status="processing", last_error=None)
        session = AsyncMock()
        session.flush = AsyncMock()

        _run(_mark_job_failed(session, job, RuntimeError("telegram 500")))

        self.assertEqual(job.status, "failed")
        self.assertIn("telegram 500", job.last_error)
        session.flush.assert_awaited_once()


class SnapshotSession:
    def __init__(self, event):
        self._event = event

    async def execute(self, _stmt):
        return FakeScalarOne(self._event)


class CaptureSnapshotTest(unittest.TestCase):
    def test_missing_event_marks_not_existing(self):
        snapshot = _run(capture_event_snapshot(SnapshotSession(None), 5))
        self.assertEqual(snapshot["event_id"], 5)
        self.assertFalse(snapshot["event_exists"])
        self.assertEqual(snapshot["detail_messages"], [])

    def test_snapshot_freezes_published_messages(self):
        chat = SimpleNamespace(
            telegram_chat_id=-100123, chat_type="supergroup", username="clubchat"
        )
        detail = SimpleNamespace(chat_id=3, chat=chat, message_id=55)
        event = SimpleNamespace(
            id=5, status="approved", category_id=2, detail_messages=[detail]
        )

        snapshot = _run(capture_event_snapshot(SnapshotSession(event), 5))

        self.assertTrue(snapshot["event_exists"])
        self.assertEqual(snapshot["status"], "approved")
        self.assertEqual(len(snapshot["detail_messages"]), 1)
        frozen = snapshot["detail_messages"][0]
        self.assertEqual(frozen["telegram_chat_id"], -100123)
        self.assertEqual(frozen["message_id"], 55)


class FakeOneResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class VersionSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, _stmt):
        return FakeOneResult(self._row)


class SyncVersionTest(unittest.TestCase):
    def test_no_completed_jobs_reports_zero(self):
        version = _run(latest_completed_sync_version(VersionSession((None, None))))
        self.assertEqual(version, {"version": 0, "completed_at": None})

    def test_reports_latest_version_and_iso_timestamp(self):
        from datetime import datetime, timezone

        completed = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        version = _run(latest_completed_sync_version(VersionSession((12, completed))))
        self.assertEqual(version["version"], 12)
        self.assertEqual(version["completed_at"], completed.isoformat())


class ApplyJobDeleteTest(unittest.TestCase):
    """Delete-like sync jobs must unpublish every Telegram detail message frozen
    in the snapshot and purge the DB rows — this is what removes a rejected /
    cancelled / deleted event from every group chat."""

    def test_delete_operation_unpublishes_and_purges_rows(self):
        worker = EventSyncWorker(bot=AsyncMock(), session_factory=AsyncMock())
        job = SimpleNamespace(
            id=1,
            operation="deleted",
            event_id=5,
            payload_json={
                "snapshot": {
                    "event_id": 5,
                    "detail_messages": [
                        {"chat_id": 3, "telegram_chat_id": -100, "message_id": 55}
                    ],
                }
            },
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)  # event already gone
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        self.assertIn("deleted", DELETE_LIKE_OPERATIONS)

        with (
            patch.object(
                event_sync, "call_with_telegram_backoff", AsyncMock()
            ) as tg_call,
            patch.object(event_sync, "_schedule_dashboard_refresh", AsyncMock()),
        ):
            _run(worker._apply_job(session, job))

        # the frozen Telegram message is deleted and the detail rows are purged
        tg_call.assert_awaited()
        session.execute.assert_awaited()
        session.flush.assert_awaited()


if __name__ == "__main__":
    unittest.main()
