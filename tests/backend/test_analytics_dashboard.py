import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from app.models.enums import ModerationAction  # noqa: E402
from app.services.analytics_dashboard import (  # noqa: E402
    _LogEntry,
    first_decision_seconds,
    review_iterations,
    total_review_seconds,
)

BASE = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _log(action: str, minutes: int) -> _LogEntry:
    return _LogEntry(action=action, created_at=BASE + timedelta(minutes=minutes))


class ReviewIterationTest(unittest.TestCase):
    """A needs_changes -> resubmit -> approved event is ONE event with N review
    passes, never double-counted across cards."""

    def test_needs_changes_then_approved_counts_two_iterations(self):
        logs = [
            _log(ModerationAction.SUBMITTED.value, 0),
            _log(ModerationAction.NEEDS_CHANGES.value, 10),
            _log(ModerationAction.RESUBMITTED.value, 20),
            _log(ModerationAction.APPROVED.value, 30),
        ]
        # resubmitted/submitted are not decisions; needs_changes + approved are
        self.assertEqual(review_iterations(logs), 2)

    def test_single_approval_is_one_iteration(self):
        logs = [
            _log(ModerationAction.SUBMITTED.value, 0),
            _log(ModerationAction.APPROVED.value, 5),
        ]
        self.assertEqual(review_iterations(logs), 1)

    def test_never_reviewed_returns_none(self):
        logs = [_log(ModerationAction.SUBMITTED.value, 0)]
        self.assertIsNone(review_iterations(logs))


class FirstDecisionTest(unittest.TestCase):
    def test_time_to_first_decision_from_submission(self):
        logs = [
            _log(ModerationAction.SUBMITTED.value, 0),
            _log(ModerationAction.NEEDS_CHANGES.value, 15),
            _log(ModerationAction.APPROVED.value, 40),
        ]
        # first decision is the needs_changes at +15 minutes
        self.assertEqual(first_decision_seconds(logs, None), 15 * 60)

    def test_falls_back_to_created_at_when_no_submitted_log(self):
        fallback = BASE - timedelta(minutes=5)
        logs = [_log(ModerationAction.APPROVED.value, 0)]
        self.assertEqual(first_decision_seconds(logs, fallback), 5 * 60)

    def test_no_decision_yet_returns_none(self):
        logs = [_log(ModerationAction.SUBMITTED.value, 0)]
        self.assertIsNone(first_decision_seconds(logs, None))


class TotalReviewTest(unittest.TestCase):
    def test_total_review_spans_submission_to_final_terminal(self):
        logs = [
            _log(ModerationAction.SUBMITTED.value, 0),
            _log(ModerationAction.NEEDS_CHANGES.value, 15),
            _log(ModerationAction.RESUBMITTED.value, 30),
            _log(ModerationAction.APPROVED.value, 60),
        ]
        # submission (0) to final approval (60 min), including the back-and-forth
        self.assertEqual(total_review_seconds(logs, None), 60 * 60)

    def test_non_terminal_only_returns_none(self):
        logs = [
            _log(ModerationAction.SUBMITTED.value, 0),
            _log(ModerationAction.NEEDS_CHANGES.value, 15),
        ]
        self.assertIsNone(total_review_seconds(logs, None))

    def test_never_negative_on_clock_skew(self):
        # a terminal log timestamped before submission must clamp to 0, not go negative
        logs = [
            _LogEntry(ModerationAction.SUBMITTED.value, BASE),
            _LogEntry(ModerationAction.APPROVED.value, BASE - timedelta(minutes=1)),
        ]
        self.assertEqual(total_review_seconds(logs, None), 0.0)


if __name__ == "__main__":
    unittest.main()
