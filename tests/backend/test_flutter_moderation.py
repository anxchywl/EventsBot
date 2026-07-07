import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from fastapi import HTTPException  # noqa: E402

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
        ):
            result = _run(
                flutter_events.resubmit_event(event.id, payload, user, session)
            )

        self.assertIs(result, sentinel)
        self.assertEqual(event.status, EventStatus.RESUBMITTED.value)
        # coming from needs_changes is a real transition, so the reviewer is pinged
        notify.assert_awaited_once()

    def test_resubmit_rejected_when_event_is_currently_approved(self):
        event = self._make_event(EventStatus.APPROVED.value)
        user = SimpleNamespace(id=7)
        session = _mock_session()
        payload = FlutterEventResubmit()

        with patch.object(
            flutter_events, "get_event_by_id", AsyncMock(return_value=event)
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(flutter_events.resubmit_event(event.id, payload, user, session))

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(event.status, EventStatus.APPROVED.value)


if __name__ == "__main__":
    unittest.main()
