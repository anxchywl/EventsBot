import asyncio
import os
import unittest
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import app.web.routers.flutter_events as fe  # noqa: E402
from app.models.enums import EventStatus  # noqa: E402
from app.web.schemas import (  # noqa: E402
    FlutterEventCancel,
    FlutterEventCreate,
    FlutterEventPatch,
    FlutterEventResubmit,
    FlutterEventStatusUpdate,
)


def _run(coro):
    return asyncio.run(coro)


def _event(**overrides):
    base = dict(
        id=42,
        public_token="tok-42",
        client_request_fingerprint=None,
        title="Robotics Night",
        description="Come build robots",
        event_date=date(2099, 5, 1),
        event_time=time(18, 0),
        event_end_time=time(20, 0),
        location="Block C",
        category_id=1,
        category=SimpleNamespace(name="Tech"),
        club_id=None,
        organizer_name="Robotics Club",
        status=EventStatus.APPROVED.value,
        poster_file_id=None,
        it_equipment=None,
        materials=None,
        registration_url=None,
        moderation_note=None,
        creator_user_id=7,
        creator=SimpleNamespace(telegram_id=7007),
        parent_event_id=None,
        timezone="Asia/Almaty",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _create_payload(**overrides):
    base = dict(
        title="Robotics Night",
        description="Come build robots",
        event_date=date(2099, 5, 1),
        event_time="18:00",
        event_end_time="20:00",
        location="Block C",
        category_id=1,
        organizer_name="Robotics Club",
        client_request_id="request_1234567890",
    )
    base.update(overrides)
    return FlutterEventCreate(**base)


class EventPayloadValidationTest(unittest.TestCase):
    def test_normalizes_single_line_fields_and_accepts_unicode(self):
        payload = _create_payload(
            title="  Robotics   Night 🎓  ",
            organizer_name="  Студенческий клуб  ",
        )
        self.assertEqual(payload.title, "Robotics Night 🎓")
        self.assertEqual(payload.organizer_name, "Студенческий клуб")

    def test_rejects_blank_required_fields_and_control_characters(self):
        for field_name, value in (
            ("title", "   "),
            ("location", "Room\x00A"),
            ("organizer_name", "Club\nAdmin"),
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValidationError):
                    _create_payload(**{field_name: value})

    def test_rejects_invalid_registration_schemes_and_whitespace(self):
        for value in (
            "javascript:alert(1)",
            "file:///tmp/form",
            "/relative",
            "https://events.example.edu/a b",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    _create_payload(registration_url=value)

    def test_accepts_http_links_with_a_real_hostname(self):
        payload = _create_payload(
            registration_url="https://events.example.edu/register?club=robotics"
        )
        self.assertEqual(
            payload.registration_url,
            "https://events.example.edu/register?club=robotics",
        )

    def test_accepts_legacy_payload_without_client_request_id(self):
        data = _create_payload().model_dump()
        data.pop("client_request_id")
        payload = FlutterEventCreate(**data)
        self.assertIsNone(payload.client_request_id)

    def test_rejects_invalid_client_request_id(self):
        with self.assertRaises(ValidationError):
            _create_payload(client_request_id="short")

    def test_patch_rejects_reversed_times(self):
        with self.assertRaises(ValidationError):
            FlutterEventPatch(event_time="20:00", event_end_time="18:00")

    def test_resubmit_rejects_explicitly_blank_core_fields(self):
        for field_name in ("title", "description", "location", "organizer_name"):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValidationError):
                    FlutterEventResubmit(**{field_name: "   "})

    def test_status_updates_only_accept_moderator_decisions(self):
        for value in ("resubmitted", "cancelled", "archived"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                FlutterEventStatusUpdate(status=value)

    def test_rejection_and_change_requests_require_a_comment(self):
        for value in ("rejected", "needs_changes"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                FlutterEventStatusUpdate(status=value, comment="   ")

    def test_lifecycle_comments_are_normalized(self):
        status_update = FlutterEventStatusUpdate(
            status="needs_changes",
            comment="  fix   the date  ",
        )
        cancellation = FlutterEventCancel(comment="   ")
        self.assertEqual(status_update.comment, "fix   the date")
        self.assertIsNone(cancellation.comment)


class SerializeEventTest(unittest.TestCase):
    def test_serializes_core_fields_and_times(self):
        item = fe._serialize_event(_event())
        self.assertEqual(item.id, 42)
        self.assertEqual(item.event_time, "18:00")
        self.assertEqual(item.event_end_time, "20:00")
        self.assertEqual(item.category, "Tech")
        self.assertIsNone(item.cover_url)

    def test_cover_url_is_versioned_by_poster_file_id(self):
        # Flutter reuses the same canonical helper as the Mini App, so the
        # `?v=<poster_file_id>` version is present on both clients — a replaced
        # cover changes the URL and busts the client's immutable image cache.
        item = fe._serialize_event(_event(poster_file_id="fid"))
        self.assertEqual(item.cover_url, "/api/events/tok-42/cover?v=fid")

    def test_cover_url_changes_when_poster_file_id_changes(self):
        # identical poster version -> identical URL (cache reuse); a new poster
        # version -> a new URL (forces a re-download of the replaced image)
        old = fe._serialize_event(_event(poster_file_id="fid-old")).cover_url
        same = fe._serialize_event(_event(poster_file_id="fid-old")).cover_url
        new = fe._serialize_event(_event(poster_file_id="fid-new")).cover_url
        self.assertEqual(old, same)
        self.assertNotEqual(old, new)

    def test_removed_cover_serializes_none(self):
        item = fe._serialize_event(_event(poster_file_id=None))
        self.assertIsNone(item.cover_url)

    def test_external_https_cover_url_is_returned_directly(self):
        item = fe._serialize_event(
            _event(poster_file_id="https://nu.edu.kz/images/event.jpg")
        )
        self.assertEqual(item.cover_url, "https://nu.edu.kz/images/event.jpg")

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


class EventMutationInvariantTest(unittest.TestCase):
    def test_create_retry_returns_the_existing_owned_event(self):
        user = SimpleNamespace(id=7)
        payload = _create_payload()
        fingerprint = fe.event_submission_fingerprint(
            payload.model_dump(mode="json", exclude={"client_request_id"})
        )
        existing = _event(
            creator_user_id=user.id,
            client_request_fingerprint=fingerprint,
        )
        session = AsyncMock()
        with (
            patch.object(fe, "acquire_event_submission_lock", AsyncMock()),
            patch.object(
                fe,
                "get_event_by_client_request_id",
                AsyncMock(return_value=existing),
            ),
            patch.object(fe, "check_rate_limit", AsyncMock()) as rate_limit,
            patch.object(fe, "create_pending_event", AsyncMock()) as create,
        ):
            result = _run(fe.submit_event(payload, user, session))

        self.assertEqual(result.id, existing.id)
        rate_limit.assert_not_awaited()
        create.assert_not_awaited()

    def test_create_retry_rejects_a_changed_payload_for_the_same_key(self):
        user = SimpleNamespace(id=7)
        existing = _event(
            creator_user_id=user.id,
            client_request_fingerprint="different",
        )
        with (
            patch.object(fe, "acquire_event_submission_lock", AsyncMock()),
            patch.object(
                fe,
                "get_event_by_client_request_id",
                AsyncMock(return_value=existing),
            ),
            patch.object(fe, "check_rate_limit", AsyncMock()) as rate_limit,
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(fe.submit_event(_create_payload(), user, AsyncMock()))

        self.assertEqual(ctx.exception.status_code, 409)
        rate_limit.assert_not_awaited()

    def test_create_rejects_an_overlapping_active_event(self):
        user = SimpleNamespace(id=7)
        session = AsyncMock()
        with (
            patch.object(fe, "acquire_event_submission_lock", AsyncMock()),
            patch.object(
                fe,
                "get_event_by_client_request_id",
                AsyncMock(return_value=None),
            ),
            patch.object(fe, "check_rate_limit", AsyncMock()),
            patch.object(
                fe,
                "get_category_by_id",
                AsyncMock(return_value=SimpleNamespace(id=1)),
            ),
            patch.object(
                fe,
                "find_event_schedule_conflict",
                AsyncMock(return_value=_event()),
            ),
            patch.object(fe, "create_pending_event", AsyncMock()) as create,
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(fe.submit_event(_create_payload(), user, session))

        self.assertEqual(ctx.exception.status_code, 409)
        create.assert_not_awaited()

    def test_resubmit_retry_returns_the_existing_update_draft(self):
        user = SimpleNamespace(id=7)
        parent = _event(creator_user_id=user.id)
        payload = FlutterEventResubmit(
            title="Updated Robotics Night",
            client_request_id="resubmit_1234567890",
        )
        fingerprint = fe.event_submission_fingerprint(
            {
                "parent_event_id": parent.id,
                **payload.model_dump(mode="json", exclude={"client_request_id"}),
            }
        )
        existing = _event(
            id=43,
            parent_event_id=parent.id,
            creator_user_id=user.id,
            client_request_fingerprint=fingerprint,
        )
        with (
            patch.object(
                fe,
                "get_event_by_id",
                AsyncMock(side_effect=[parent, parent]),
            ),
            patch.object(fe, "acquire_event_submission_lock", AsyncMock()),
            patch.object(
                fe,
                "get_event_by_client_request_id",
                AsyncMock(return_value=existing),
            ),
            patch.object(fe, "check_rate_limit", AsyncMock()) as rate_limit,
            patch.object(fe, "create_event_update_draft", AsyncMock()) as create,
        ):
            result = _run(fe.resubmit_event(parent.id, payload, user, AsyncMock()))

        self.assertEqual(result.id, existing.id)
        rate_limit.assert_not_awaited()
        create.assert_not_awaited()

    def test_partial_resubmit_cannot_reverse_the_persisted_time_range(self):
        user = SimpleNamespace(id=7)
        event = _event(
            status=EventStatus.NEEDS_CHANGES.value,
            creator_user_id=user.id,
        )
        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "check_rate_limit", AsyncMock()),
            patch.object(fe, "acquire_event_submission_lock", AsyncMock()),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(
                    fe.resubmit_event(
                        event.id,
                        FlutterEventResubmit(event_end_time="17:00"),
                        user,
                        AsyncMock(),
                    )
                )
        self.assertEqual(ctx.exception.status_code, 422)

    def test_resubmit_can_clear_optional_text_fields(self):
        user = SimpleNamespace(id=7)
        event = _event(
            status=EventStatus.NEEDS_CHANGES.value,
            creator_user_id=user.id,
            registration_url="https://events.example.edu/register",
        )
        session = AsyncMock()
        session.add = lambda *args, **kwargs: None
        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "check_rate_limit", AsyncMock()),
            patch.object(fe, "acquire_event_submission_lock", AsyncMock()),
            patch.object(
                fe,
                "find_event_schedule_conflict",
                AsyncMock(return_value=None),
            ),
            patch.object(fe, "_notify_reviewer_of_resubmission", AsyncMock()),
        ):
            _run(
                fe.resubmit_event(
                    event.id,
                    FlutterEventResubmit(registration_url=""),
                    user,
                    session,
                )
            )

        self.assertIsNone(event.registration_url)


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
        event = _event(status=EventStatus.PENDING.value)
        session = AsyncMock()

        async def approve(_session, current, _status, _admin, _comment, **_kwargs):
            current.status = EventStatus.APPROVED.value
            return current

        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "_acquire_moderation_lock", AsyncMock(return_value=True)),
            patch.object(fe, "_release_moderation_lock", AsyncMock()) as release,
            patch.object(fe, "acquire_event_lock", AsyncMock()),
            patch.object(fe, "acquire_event_submission_lock", AsyncMock()),
            patch.object(fe, "capture_event_snapshot", AsyncMock(return_value={})),
            patch.object(fe, "event_has_ended", return_value=False),
            patch.object(
                fe,
                "find_event_schedule_conflict",
                AsyncMock(return_value=None),
            ),
            patch.object(
                fe,
                "apply_moderation_transition",
                AsyncMock(side_effect=approve),
            ),
            patch.object(fe, "enqueue_event_sync", AsyncMock()) as enqueue,
            patch.object(
                fe,
                "_publish_event_status_change",
                AsyncMock(),
            ) as publish,
            patch.object(fe, "_publish_event_deleted", AsyncMock()),
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

    def test_terminal_event_cannot_be_reapproved(self):
        admin = SimpleNamespace(id=1, role="admin")
        event = _event(status=EventStatus.CANCELLED.value)
        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "_acquire_moderation_lock", AsyncMock(return_value=True)),
            patch.object(fe, "_release_moderation_lock", AsyncMock()),
            patch.object(fe, "acquire_event_lock", AsyncMock()),
            patch.object(fe, "apply_moderation_transition", AsyncMock()) as apply,
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(fe.moderate_event(42, self._payload(), admin, AsyncMock()))

        self.assertEqual(ctx.exception.status_code, 409)
        apply.assert_not_awaited()

    def test_past_event_cannot_be_approved(self):
        admin = SimpleNamespace(id=1, role="admin")
        event = _event(status=EventStatus.PENDING.value)
        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "_acquire_moderation_lock", AsyncMock(return_value=True)),
            patch.object(fe, "_release_moderation_lock", AsyncMock()),
            patch.object(fe, "acquire_event_lock", AsyncMock()),
            patch.object(fe, "event_has_ended", return_value=True),
            patch.object(fe, "apply_moderation_transition", AsyncMock()) as apply,
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(fe.moderate_event(42, self._payload(), admin, AsyncMock()))

        self.assertEqual(ctx.exception.status_code, 409)
        apply.assert_not_awaited()


class CreatorLifecycleTest(unittest.TestCase):
    def test_stranger_cannot_cancel_an_event(self):
        event = _event(status=EventStatus.PENDING.value, creator_user_id=7)
        stranger = SimpleNamespace(id=8, role="user")
        with patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)):
            with self.assertRaises(HTTPException) as ctx:
                _run(
                    fe.cancel_event(
                        event.id,
                        FlutterEventCancel(),
                        stranger,
                        AsyncMock(),
                    )
                )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_owner_can_cancel_an_active_event(self):
        event = _event(status=EventStatus.APPROVED.value, creator_user_id=7)
        owner = SimpleNamespace(id=7, role="user")
        session = AsyncMock()

        async def cancel(_session, _event_id, _status, _user, _comment):
            event.status = EventStatus.CANCELLED.value
            return event

        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "acquire_event_lock", AsyncMock()),
            patch.object(fe, "capture_event_snapshot", AsyncMock(return_value={})),
            patch.object(fe, "update_event_status", AsyncMock(side_effect=cancel)),
            patch.object(fe, "enqueue_event_sync", AsyncMock()) as enqueue,
            patch.object(fe, "_publish_event_status_change", AsyncMock()) as publish,
            patch.object(fe, "_notify_creator", AsyncMock()),
        ):
            result = _run(
                fe.cancel_event(event.id, FlutterEventCancel(), owner, session)
            )

        self.assertEqual(result.status, EventStatus.CANCELLED.value)
        enqueue.assert_awaited_once()
        publish.assert_awaited_once()

    def test_active_event_must_be_cancelled_before_deletion(self):
        event = _event(status=EventStatus.APPROVED.value, creator_user_id=7)
        owner = SimpleNamespace(id=7, role="user")
        with patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)):
            with self.assertRaises(HTTPException) as ctx:
                _run(fe.delete_event(event.id, owner, AsyncMock()))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_terminal_event_deletion_is_idempotent(self):
        event = _event(status=EventStatus.CANCELLED.value, creator_user_id=7)
        owner = SimpleNamespace(id=7, role="user")
        session = AsyncMock()
        with (
            patch.object(fe, "get_event_by_id", AsyncMock(return_value=event)),
            patch.object(fe, "delete_event_completely", AsyncMock(return_value=True)),
            patch.object(fe, "_publish_event_deleted", AsyncMock()) as publish,
        ):
            response = _run(fe.delete_event(event.id, owner, session))

        self.assertEqual(response.status_code, 204)
        publish.assert_awaited_once()

        with patch.object(fe, "get_event_by_id", AsyncMock(return_value=None)):
            response = _run(fe.delete_event(event.id, owner, AsyncMock()))
        self.assertEqual(response.status_code, 204)


if __name__ == "__main__":
    unittest.main()
