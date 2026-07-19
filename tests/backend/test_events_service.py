import asyncio
import os
import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from app.models.enums import EventStatus, ModerationAction  # noqa: E402
from app.models.event import Event  # noqa: E402
from app.models.moderation import ModerationLog  # noqa: E402
from app.services.events import (  # noqa: E402
    can_moderate_event_status,
    ensure_event_public_token,
    event_belongs_to_telegram_user,
    event_has_ended,
    find_event_schedule_conflict,
    get_pending_events,
    normalize_public_token,
    update_event_status,
)


def _run(coro):
    return asyncio.run(coro)


class TokenHelpersTest(unittest.TestCase):
    def test_normalize_strips_prefix_and_whitespace(self):
        self.assertEqual(normalize_public_token("  event_abc  "), "abc")
        self.assertEqual(normalize_public_token("event_abc"), "abc")
        self.assertEqual(normalize_public_token("abc"), "abc")

    def test_ensure_token_only_mints_when_missing(self):
        existing = SimpleNamespace(public_token="keep-me")
        self.assertEqual(ensure_event_public_token(existing), "keep-me")

        fresh = SimpleNamespace(public_token=None)
        minted = ensure_event_public_token(fresh)
        self.assertTrue(minted)
        self.assertEqual(fresh.public_token, minted)

    def test_telegram_ownership_uses_telegram_id_not_internal_user_id(self):
        event = SimpleNamespace(
            creator_user_id=2,
            creator=SimpleNamespace(telegram_id=999),
        )
        self.assertFalse(event_belongs_to_telegram_user(event, 2))
        self.assertTrue(event_belongs_to_telegram_user(event, 999))


class FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalars(self._rows)


class PendingSession:
    def __init__(self, events):
        self._events = events

    async def execute(self, _stmt):
        return FakeListResult(self._events)


def _pending(event_id, status, minutes, parent=None):
    return SimpleNamespace(
        id=event_id,
        status=status,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        + timedelta(minutes=minutes),
        parent_event_id=parent,
    )


class PendingQueueTest(unittest.TestCase):
    def test_dedupes_drafts_to_the_latest_per_source(self):
        # two drafts of the same parent -> only the newest survives the queue
        old = _pending(1, EventStatus.PENDING.value, 0, parent=100)
        new = _pending(2, EventStatus.PENDING.value, 30, parent=100)
        session = PendingSession([old, new])

        result = _run(get_pending_events(session))

        self.assertEqual([e.id for e in result], [2])

    def test_orders_resubmitted_before_needs_changes_before_pending(self):
        pending = _pending(1, EventStatus.PENDING.value, 0)
        needs = _pending(2, EventStatus.NEEDS_CHANGES.value, 0)
        resubmitted = _pending(3, EventStatus.RESUBMITTED.value, 0)
        session = PendingSession([pending, needs, resubmitted])

        result = _run(get_pending_events(session))

        # resubmitted (creator waiting) first, then needs_changes, then pending
        self.assertEqual([e.id for e in result], [3, 2, 1])


def _scheduled_event(
    event_id,
    start,
    end,
    location="Block C",
):
    return SimpleNamespace(
        id=event_id,
        status=EventStatus.APPROVED.value,
        event_date=date(2099, 5, 1),
        event_time=start,
        event_end_time=end,
        location=location,
    )


class EventScheduleConflictTest(unittest.TestCase):
    def test_detects_only_real_time_overlap_at_the_same_location(self):
        existing = _scheduled_event(1, time(18, 0), time(20, 0))
        session = PendingSession([existing])

        overlap = _run(
            find_event_schedule_conflict(
                session,
                event_date=date(2099, 5, 1),
                event_time=time(19, 0),
                event_end_time=time(21, 0),
                location="  block   c ",
            )
        )
        adjacent = _run(
            find_event_schedule_conflict(
                session,
                event_date=date(2099, 5, 1),
                event_time=time(20, 0),
                event_end_time=time(21, 0),
                location="Block C",
            )
        )

        self.assertIs(overlap, existing)
        self.assertIsNone(adjacent)

    def test_excludes_the_event_being_resubmitted(self):
        existing = _scheduled_event(1, time(18, 0), time(20, 0))
        session = PendingSession([existing])
        result = _run(
            find_event_schedule_conflict(
                session,
                event_date=date(2099, 5, 1),
                event_time=time(18, 0),
                event_end_time=time(20, 0),
                location="Block C",
                exclude_event_id=1,
            )
        )
        self.assertIsNone(result)

    def test_legacy_events_without_end_time_reserve_one_hour(self):
        existing = _scheduled_event(1, time(18, 0), None)
        session = PendingSession([existing])
        result = _run(
            find_event_schedule_conflict(
                session,
                event_date=date(2099, 5, 1),
                event_time=time(18, 30),
                event_end_time=time(19, 30),
                location="Block C",
            )
        )
        self.assertIs(result, existing)

    def test_client_request_id_has_a_unique_database_index(self):
        indexes = {index.name: index for index in Event.__table__.indexes}
        self.assertIn("ix_events_client_request_id", indexes)
        self.assertTrue(indexes["ix_events_client_request_id"].unique)
        self.assertEqual(Event.client_request_fingerprint.type.length, 64)

    def test_multiple_event_ids_can_be_excluded_for_draft_approval(self):
        parent = _scheduled_event(1, time(18, 0), time(20, 0))
        draft = _scheduled_event(2, time(19, 0), time(21, 0))
        session = PendingSession([parent, draft])
        result = _run(
            find_event_schedule_conflict(
                session,
                event_date=date(2099, 5, 1),
                event_time=time(19, 0),
                event_end_time=time(21, 0),
                location="Block C",
                exclude_event_ids={1, 2},
            )
        )
        self.assertIsNone(result)


class LifecyclePolicyTest(unittest.TestCase):
    def test_terminal_states_cannot_be_moderated(self):
        for current in (EventStatus.CANCELLED.value, EventStatus.ARCHIVED.value):
            with self.subTest(current=current):
                self.assertFalse(
                    can_moderate_event_status(current, EventStatus.APPROVED)
                )

    def test_rejected_event_can_be_reconsidered(self):
        self.assertTrue(
            can_moderate_event_status(
                EventStatus.REJECTED.value,
                EventStatus.APPROVED,
            )
        )

    def test_event_end_uses_its_declared_timezone(self):
        event = SimpleNamespace(
            event_date=date(2026, 7, 19),
            event_time=time(10, 0),
            event_end_time=time(12, 0),
            timezone="Asia/Almaty",
        )
        before_end = datetime(2026, 7, 19, 6, 59, tzinfo=timezone.utc)
        after_end = datetime(2026, 7, 19, 7, 1, tzinfo=timezone.utc)
        self.assertFalse(event_has_ended(event, now=before_end))
        self.assertTrue(event_has_ended(event, now=after_end))


class FakeScalarOne:
    def __init__(self, event):
        self._event = event

    def scalar_one_or_none(self):
        return self._event


class StatusSession:
    def __init__(self, event):
        self._event = event
        self.added = []
        self.flushed = 0

    async def execute(self, _stmt):
        return FakeScalarOne(self._event)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1


def _event(status):
    return SimpleNamespace(
        id=42,
        status=status,
        approved_by_user_id=None,
        approved_at=None,
        archived_at=None,
        restored_at=None,
        moderation_note=None,
    )


def _admin():
    return SimpleNamespace(id=9)


class StatusTransitionTest(unittest.TestCase):
    def _logs(self, session):
        return [obj for obj in session.added if isinstance(obj, ModerationLog)]

    def test_approve_sets_approval_metadata_and_logs_approved(self):
        event = _event(EventStatus.PENDING.value)
        session = StatusSession(event)

        _run(update_event_status(session, 42, EventStatus.APPROVED, _admin(), "ok"))

        self.assertEqual(event.status, EventStatus.APPROVED.value)
        self.assertEqual(event.approved_by_user_id, 9)
        self.assertIsNotNone(event.approved_at)
        self.assertIsNone(event.restored_at)
        self.assertEqual(event.moderation_note, "ok")
        log = self._logs(session)[0]
        self.assertEqual(log.action, ModerationAction.APPROVED.value)

    def test_restore_from_archived_uses_restored_action_and_timestamp(self):
        event = _event(EventStatus.ARCHIVED.value)
        session = StatusSession(event)

        _run(update_event_status(session, 42, EventStatus.APPROVED, _admin()))

        self.assertEqual(event.status, EventStatus.APPROVED.value)
        self.assertIsNotNone(event.restored_at)
        self.assertEqual(event.restored_at, event.approved_at)
        self.assertEqual(self._logs(session)[0].action, ModerationAction.RESTORED.value)

    def test_archive_sets_archived_at_and_logs_archived(self):
        event = _event(EventStatus.APPROVED.value)
        session = StatusSession(event)

        _run(update_event_status(session, 42, EventStatus.ARCHIVED, _admin()))

        self.assertEqual(event.status, EventStatus.ARCHIVED.value)
        self.assertIsNotNone(event.archived_at)
        self.assertEqual(self._logs(session)[0].action, ModerationAction.ARCHIVED.value)

    def test_needs_changes_logs_needs_changes_with_comment(self):
        event = _event(EventStatus.PENDING.value)
        session = StatusSession(event)

        _run(
            update_event_status(
                session, 42, EventStatus.NEEDS_CHANGES, _admin(), "fix the date"
            )
        )

        log = self._logs(session)[0]
        self.assertEqual(log.action, ModerationAction.NEEDS_CHANGES.value)
        self.assertEqual(log.comment, "fix the date")

    def test_missing_event_returns_none(self):
        session = StatusSession(None)
        result = _run(update_event_status(session, 42, EventStatus.APPROVED, _admin()))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
