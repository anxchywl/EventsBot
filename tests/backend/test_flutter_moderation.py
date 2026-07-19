import asyncio
import os
import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import app.web.routers.flutter_events as flutter_events  # noqa: E402
from app.models.enums import EventStatus  # noqa: E402
from app.web.schemas import FlutterEventResubmit  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    # session.add is synchronous; keep it from returning an un-awaited coroutine
    session.add = lambda *args, **kwargs: None
    return session


class ResubmitAfterAdminTransitionTest(unittest.TestCase):
    """Regression: the resubmit gate must depend only on the event's *current*
    status, not its history. The admin post-approval control surface can drop a
    previously-approved (or previously-rejected) event back to `needs_changes`;
    the creator must still be able to resubmit it from there.
    """

    def _make_event(self, status: str):
        return SimpleNamespace(
            id=42,
            creator_user_id=7,
            category_id=1,
            status=status,
            parent_event_id=None,
            title="Robotics night",
            description="Build a robot",
            event_date=date(2099, 5, 1),
            event_time=time(18, 0),
            event_end_time=time(20, 0),
            location="Block C",
            club_id=None,
            timezone="Asia/Almaty",
            organizer_name="Robotics Club",
            poster_file_id=None,
            it_equipment=None,
            materials=None,
            registration_url=None,
            creator=SimpleNamespace(first_name="Ann"),
        )

    def test_resubmit_allowed_after_admin_needs_changes_on_approved_event(self):
        event = self._make_event(EventStatus.NEEDS_CHANGES.value)
        user = SimpleNamespace(id=7)
        session = _mock_session()
        payload = FlutterEventResubmit()
        sentinel = object()

        with (
            patch.object(
                flutter_events, "get_event_by_id", AsyncMock(return_value=event)
            ),
            patch.object(flutter_events, "_serialize_event", return_value=sentinel),
            patch.object(
                flutter_events,
                "_notify_reviewer_of_resubmission",
                AsyncMock(),
            ) as notify,
            patch.object(
                flutter_events,
                "acquire_event_submission_lock",
                AsyncMock(),
            ),
            patch.object(
                flutter_events,
                "find_event_schedule_conflict",
                AsyncMock(return_value=None),
            ),
            patch.object(flutter_events, "check_rate_limit", AsyncMock()),
        ):
            result = _run(
                flutter_events.resubmit_event(event.id, payload, user, session)
            )

        self.assertIs(result, sentinel)
        self.assertEqual(event.status, EventStatus.RESUBMITTED.value)
        # coming from needs_changes is a real transition, so the reviewer is pinged
        notify.assert_awaited_once()

    def test_approved_event_edit_creates_draft_without_mutating_parent(self):
        event = self._make_event(EventStatus.APPROVED.value)
        draft = SimpleNamespace(id=43)
        loaded_draft = SimpleNamespace(id=43)
        user = SimpleNamespace(id=7)
        session = _mock_session()
        payload = FlutterEventResubmit(title="Updated robotics night")
        sentinel = object()

        with (
            patch.object(
                flutter_events,
                "get_event_by_id",
                AsyncMock(side_effect=[event, event, loaded_draft]),
            ),
            patch.object(
                flutter_events,
                "acquire_event_submission_lock",
                AsyncMock(),
            ),
            patch.object(
                flutter_events,
                "find_event_schedule_conflict",
                AsyncMock(return_value=None),
            ),
            patch.object(flutter_events, "check_rate_limit", AsyncMock()),
            patch.object(
                flutter_events,
                "create_event_update_draft",
                AsyncMock(return_value=draft),
            ) as create_draft,
            patch.object(
                flutter_events,
                "_serialize_event",
                return_value=sentinel,
            ),
        ):
            result = _run(
                flutter_events.resubmit_event(event.id, payload, user, session)
            )

        self.assertIs(result, sentinel)
        self.assertEqual(event.status, EventStatus.APPROVED.value)
        self.assertEqual(event.title, "Robotics night")
        self.assertEqual(
            create_draft.await_args.kwargs["event_data"]["title"],
            "Updated robotics night",
        )


if __name__ == "__main__":
    unittest.main()
