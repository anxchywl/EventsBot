import asyncio
import os
import unittest
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from fastapi import HTTPException  # noqa: E402

import app.web.routers.flutter_events as fe  # noqa: E402
from app.models.enums import EventStatus  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _event(**overrides):
    base = dict(
        id=42,
        public_token="tok-42",
        title="Robotics Night",
        description="Come build robots",
        event_date=date(2099, 5, 1),
        event_time=time(18, 0),
        event_end_time=time(20, 0),
        location="Block C",
        category=SimpleNamespace(name="Tech"),
        organizer_name="Robotics Club",
        status=EventStatus.APPROVED.value,
        poster_file_id=None,
        it_equipment=None,
        materials=None,
        registration_url=None,
        moderation_note=None,
        creator_user_id=7,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class SerializeEventTest(unittest.TestCase):
    def test_serializes_core_fields_and_times(self):
        item = fe._serialize_event(_event())
        self.assertEqual(item.id, 42)
        self.assertEqual(item.event_time, "18:00")
        self.assertEqual(item.event_end_time, "20:00")
        self.assertEqual(item.category, "Tech")
        self.assertIsNone(item.cover_url)

    def test_cover_url_present_only_with_poster(self):
        item = fe._serialize_event(_event(poster_file_id="fid"))
        self.assertEqual(item.cover_url, "/api/events/tok-42/cover")

    def test_missing_end_time_serializes_none(self):
        item = fe._serialize_event(_event(event_end_time=None))
        self.assertIsNone(item.event_end_time)


class CreatorStatusMessageTest(unittest.TestCase):
    def test_each_status_has_a_tailored_message(self):
        approved = fe._creator_status_message("Gala", EventStatus.APPROVED.value)
        rejected = fe._creator_status_message("Gala", EventStatus.REJECTED.value)
        needs = fe._creator_status_message("Gala", EventStatus.NEEDS_CHANGES.value)
        self.assertIn("approved", approved.lower())
        self.assertIn("not approved", rejected.lower())
        self.assertIn("edit", needs.lower())
        # every message embeds the event title
        for msg in (approved, rejected, needs):
            self.assertIn("Gala", msg)

    def test_unknown_status_falls_back_to_generic_update(self):
        msg = fe._creator_status_message("Gala", "some_new_status")
        self.assertIn("updated", msg.lower())


class GetEventVisibilityTest(unittest.TestCase):
    """IDOR guard: a non-admin may only open an event that is approved or that
    they created — a stranger must not read someone else's pending draft."""

    def _call(self, event, user):
        with patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)):
            return _run(fe.get_event(event.id, user, session=AsyncMock()))

    def test_stranger_cannot_read_pending_event(self):
        event = _event(status=EventStatus.PENDING.value, creator_user_id=7)
        stranger = SimpleNamespace(id=999, role="user")
        with self.assertRaises(HTTPException) as ctx:
            self._call(event, stranger)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_owner_can_read_own_pending_event(self):
        event = _event(status=EventStatus.PENDING.value, creator_user_id=7)
        owner = SimpleNamespace(id=7, role="user")
        item = self._call(event, owner)
        self.assertEqual(item.id, event.id)

    def test_admin_can_read_any_event(self):
        event = _event(status=EventStatus.NEEDS_CHANGES.value, creator_user_id=7)
        admin = SimpleNamespace(id=1, role="admin")
        item = self._call(event, admin)
        self.assertEqual(item.id, event.id)

    def test_anyone_can_read_approved_event(self):
        event = _event(status=EventStatus.APPROVED.value, creator_user_id=7)
        stranger = SimpleNamespace(id=999, role="user")
        item = self._call(event, stranger)
        self.assertEqual(item.id, event.id)

    def test_missing_event_is_404(self):
        with patch.object(fe, "get_event_by_id", AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as ctx:
                _run(
                    fe.get_event(123, SimpleNamespace(id=1, role="admin"), AsyncMock())
                )
        self.assertEqual(ctx.exception.status_code, 404)


class ModerationLockTest(unittest.TestCase):
    def test_lock_fails_open_when_redis_unavailable(self):
        # a redis outage must never hard-block moderation; the DB advisory lock
        # still serializes the write
        broken = SimpleNamespace(set=AsyncMock(side_effect=RuntimeError("redis down")))
        with patch("app.db.redis.get_redis", return_value=broken):
            self.assertTrue(_run(fe._acquire_moderation_lock(42)))

    def test_lock_reflects_redis_setnx_result(self):
        held = SimpleNamespace(set=AsyncMock(return_value=None))  # key already exists
        with patch("app.db.redis.get_redis", return_value=held):
            self.assertFalse(_run(fe._acquire_moderation_lock(42)))


class ModerateEventTest(unittest.TestCase):
    def _payload(self, status=EventStatus.APPROVED.value, comment="looks good"):
        return SimpleNamespace(status=status, comment=comment)

    def test_concurrent_moderator_is_rejected_with_409(self):
        admin = SimpleNamespace(id=1, role="admin")
        event = _event()
        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "_acquire_moderation_lock", AsyncMock(return_value=False)),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(fe.moderate_event(42, self._payload(), admin, AsyncMock()))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_successful_moderation_runs_sync_and_notifies(self):
        admin = SimpleNamespace(id=1, role="admin")
        event = _event(status=EventStatus.APPROVED.value)
        session = AsyncMock()

        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "_acquire_moderation_lock", AsyncMock(return_value=True)),
            patch.object(fe, "_release_moderation_lock", AsyncMock()) as release,
            patch.object(fe, "acquire_event_lock", AsyncMock()),
            patch.object(fe, "capture_event_snapshot", AsyncMock(return_value={})),
            patch.object(fe, "update_event_status", AsyncMock(return_value=event)),
            patch.object(fe, "enqueue_event_sync", AsyncMock()) as enqueue,
            patch.object(fe, "publish_miniapp_event", AsyncMock()) as publish,
            patch.object(fe, "_notify_creator", AsyncMock()) as notify,
        ):
            result = _run(fe.moderate_event(42, self._payload(), admin, session))

        self.assertEqual(result.id, 42)
        # the moderation decision is pushed through the sync pipeline...
        enqueue.assert_awaited_once()
        self.assertEqual(
            enqueue.await_args.kwargs["operation"], EventStatus.APPROVED.value
        )
        # ...broadcast to mini-app clients, and the creator is told
        publish.assert_awaited_once()
        notify.assert_awaited_once()
        # the concurrency lock is always released
        release.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
