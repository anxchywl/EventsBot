import asyncio
import io
import os
import struct
import unittest
import zlib
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SESSION_SECRET", "test-secret")

from PIL import Image  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import app.services.cover_storage as cover_storage  # noqa: E402
import app.web.routers.flutter_events as flutter_events  # noqa: E402
from app.services.cover_storage import (  # noqa: E402
    CoverUploadError,
    validate_cover_bytes,
)
from app.web.schemas import FlutterEventCreate  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _jpeg_bytes(size=(16, 16)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


def _png_bytes(size=(16, 16)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 200, 30)).save(buf, "PNG")
    return buf.getvalue()


def _bomb_png() -> bytes:
    # oversized ihdr fails before pixel allocation
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 100000, 100000, 8, 2, 0, 0, 0)
    ihdr = b"IHDR" + ihdr_data
    ihdr_chunk = (
        struct.pack(">I", len(ihdr_data))
        + ihdr
        + struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
    )
    iend = (
        struct.pack(">I", 0)
        + b"IEND"
        + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    )
    return sig + ihdr_chunk + iend


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)

    async def eval(self, _script, _key_count, key, expected_owner):
        owner = self.store.get(key)
        if owner != expected_owner:
            return False
        self.store.pop(key, None)
        return owner


class ValidateCoverBytesTest(unittest.TestCase):
    def _assert_status(self, raw, filename, content_type, status):
        with self.assertRaises(CoverUploadError) as ctx:
            validate_cover_bytes(raw, filename, content_type)
        self.assertEqual(ctx.exception.status_code, status)

    def test_happy_path_returns_jpeg(self):
        out = validate_cover_bytes(_png_bytes(), "photo.png", "image/png")
        self.assertTrue(out.startswith(b"\xff\xd8\xff"))

    def test_empty_file_rejected_400(self):
        self._assert_status(b"", "photo.jpg", "image/jpeg", 400)

    def test_oversized_rejected_413(self):
        raw = b"\xff\xd8\xff" + b"\x00" * 5_000_001
        self._assert_status(raw, "photo.jpg", "image/jpeg", 413)

    def test_bad_extension_rejected_415(self):
        self._assert_status(_jpeg_bytes(), "photo.txt", "image/jpeg", 415)

    def test_disallowed_content_type_rejected_415(self):
        self._assert_status(_jpeg_bytes(), "photo.jpg", "application/pdf", 415)

    def test_bad_magic_bytes_rejected_415(self):
        self._assert_status(b"NOT-AN-IMAGE" * 8, "photo.jpg", "image/jpeg", 415)

    def test_spoofed_mime_and_extension_rejected_415(self):
        self._assert_status(_jpeg_bytes(), "photo.png", "image/png", 415)

    def test_corrupt_image_rejected_422(self):
        corrupt = b"\x89PNG\r\n\x1a\n" + b"garbage-not-a-real-png"
        self._assert_status(corrupt, "photo.png", "image/png", 422)

    def test_decompression_bomb_rejected(self):
        with self.assertRaises(CoverUploadError) as ctx:
            validate_cover_bytes(_bomb_png(), "photo.png", "image/png")
        self.assertIn(ctx.exception.status_code, (413, 422))


class StagingTokenTest(unittest.TestCase):
    # telegram is only hit when a staged cover is consumed. store_cover returns
    # (file_id, storage_message_id); the message id lets orphaned images be
    # cleaned up on revalidation / commit failure.
    def _patches(self, meta, blobs, *, store=("FID", 111), revalidate=True):
        return (
            patch.object(cover_storage, "get_redis", return_value=meta),
            patch.object(cover_storage, "get_media_redis", return_value=blobs),
            patch.object(cover_storage, "store_cover", AsyncMock(return_value=store)),
            patch.object(
                cover_storage,
                "revalidate_stored_cover",
                AsyncMock(return_value=revalidate),
            ),
            patch.object(cover_storage, "delete_stored_cover_message", AsyncMock()),
        )

    def test_stage_then_consume_sends_to_telegram_once(self):
        meta, blobs = FakeRedis(), FakeRedis()
        p = self._patches(meta, blobs)
        with p[0], p[1], p[2] as store, p[3], p[4]:
            token = _run(cover_storage.stage_cover_bytes(b"cleanbytes", user_id=7))
            first = _run(cover_storage.consume_and_store_cover(token, user_id=7))
            second = _run(cover_storage.consume_and_store_cover(token, user_id=7))
        self.assertEqual(first, "FID")
        self.assertIsNone(second)
        store.assert_awaited_once_with(b"cleanbytes")

    def test_consume_appends_storage_message_id_for_cleanup(self):
        meta, blobs = FakeRedis(), FakeRedis()
        p = self._patches(meta, blobs)
        sent: list[int] = []
        with p[0], p[1], p[2], p[3], p[4]:
            token = _run(cover_storage.stage_cover_bytes(b"clean", user_id=7))
            file_id = _run(
                cover_storage.consume_and_store_cover(
                    token, user_id=7, sent_messages=sent
                )
            )
        self.assertEqual(file_id, "FID")
        self.assertEqual(sent, [111])

    def test_foreign_user_cannot_consume_and_nothing_sent(self):
        meta, blobs = FakeRedis(), FakeRedis()
        p = self._patches(meta, blobs)
        with p[0], p[1], p[2] as store, p[3], p[4]:
            token = _run(cover_storage.stage_cover_bytes(b"x", user_id=7))
            stolen = _run(cover_storage.consume_and_store_cover(token, user_id=99))
        self.assertIsNone(stolen)
        store.assert_not_awaited()

    def test_forged_or_missing_token_returns_none(self):
        meta, blobs = FakeRedis(), FakeRedis()
        p = self._patches(meta, blobs)
        with p[0], p[1], p[2], p[3], p[4]:
            self.assertIsNone(
                _run(cover_storage.consume_and_store_cover("nope", user_id=7))
            )
            self.assertIsNone(
                _run(cover_storage.consume_and_store_cover("", user_id=7))
            )

    def test_unverifiable_upload_raises_502_and_deletes_orphan(self):
        meta, blobs = FakeRedis(), FakeRedis()
        p = self._patches(meta, blobs, revalidate=False)
        with p[0], p[1], p[2], p[3], p[4] as delete_orphan:
            token = _run(cover_storage.stage_cover_bytes(b"x", user_id=7))
            with self.assertRaises(CoverUploadError) as ctx:
                _run(cover_storage.consume_and_store_cover(token, user_id=7))
        self.assertEqual(ctx.exception.status_code, 502)
        # the already-sent image must be removed so it does not orphan
        delete_orphan.assert_awaited_once_with(111)


class UploadEndpointTest(unittest.TestCase):
    def _file(self, data=b"data", filename="c.jpg", content_type="image/jpeg"):
        return SimpleNamespace(
            read=AsyncMock(return_value=data),
            filename=filename,
            content_type=content_type,
        )

    def test_unconfigured_storage_returns_503(self):
        user = SimpleNamespace(id=7)
        settings = SimpleNamespace(
            media_storage_chat_id=None, media_max_upload_bytes=5_000_000
        )
        with (
            patch.object(flutter_events, "check_rate_limit", AsyncMock()),
            patch.object(flutter_events, "get_settings", return_value=settings),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(flutter_events.upload_cover(self._file(), user))
        self.assertEqual(ctx.exception.status_code, 503)

    def test_rate_limit_trips(self):
        user = SimpleNamespace(id=7)
        with patch.object(
            flutter_events,
            "check_rate_limit",
            AsyncMock(side_effect=HTTPException(429, "slow down")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(flutter_events.upload_cover(self._file(), user))
        self.assertEqual(ctx.exception.status_code, 429)

    def test_validation_error_propagates_status(self):
        user = SimpleNamespace(id=7)
        settings = SimpleNamespace(
            media_storage_chat_id=123, media_max_upload_bytes=5_000_000
        )
        with (
            patch.object(flutter_events, "check_rate_limit", AsyncMock()),
            patch.object(flutter_events, "get_settings", return_value=settings),
            patch.object(
                flutter_events,
                "validate_cover_bytes",
                side_effect=CoverUploadError(422, "corrupt"),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(flutter_events.upload_cover(self._file(), user))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_happy_path_returns_cover_ref(self):
        user = SimpleNamespace(id=7)
        settings = SimpleNamespace(
            media_storage_chat_id=123, media_max_upload_bytes=5_000_000
        )
        with (
            patch.object(flutter_events, "check_rate_limit", AsyncMock()),
            patch.object(flutter_events, "get_settings", return_value=settings),
            patch.object(flutter_events, "validate_cover_bytes", return_value=b"clean"),
            patch.object(
                flutter_events, "stage_cover_bytes", AsyncMock(return_value="TOKEN")
            ) as stage,
        ):
            result = _run(flutter_events.upload_cover(self._file(), user))
        self.assertEqual(result, {"cover_ref": "TOKEN"})
        stage.assert_awaited_once()


class ApplyCoverChangeTest(unittest.TestCase):
    def test_remove_clears_and_busts_cache(self):
        event = SimpleNamespace(poster_file_id="old-id", poster_storage_message_id=555)
        orphaned: list[int] = []
        with patch.object(flutter_events, "bust_cover_cache", AsyncMock()) as bust:
            _run(
                flutter_events._apply_cover_change(
                    event,
                    cover_ref=None,
                    remove_cover=True,
                    user_id=7,
                    sent_messages=[],
                    orphaned_messages=orphaned,
                )
            )
        self.assertIsNone(event.poster_file_id)
        # the removed cover's storage image is queued for deletion
        self.assertIsNone(event.poster_storage_message_id)
        self.assertEqual(orphaned, [555])
        bust.assert_awaited_once_with("old-id")

    def test_replace_busts_old_and_sets_new(self):
        event = SimpleNamespace(poster_file_id="old-id", poster_storage_message_id=555)
        orphaned: list[int] = []

        async def _store(_ref, _uid, *, sent_messages):
            sent_messages.append(999)
            return "new-id"

        with (
            patch.object(
                flutter_events,
                "consume_and_store_cover",
                AsyncMock(side_effect=_store),
            ),
            patch.object(flutter_events, "bust_cover_cache", AsyncMock()) as bust,
        ):
            _run(
                flutter_events._apply_cover_change(
                    event,
                    cover_ref="tok",
                    remove_cover=False,
                    user_id=7,
                    sent_messages=[],
                    orphaned_messages=orphaned,
                )
            )
        self.assertEqual(event.poster_file_id, "new-id")
        # new storage image is tracked; the replaced one is queued for deletion
        self.assertEqual(event.poster_storage_message_id, 999)
        self.assertEqual(orphaned, [555])
        bust.assert_awaited_once_with("old-id")

    def test_forged_cover_ref_rejected(self):
        event = SimpleNamespace(poster_file_id=None, poster_storage_message_id=None)
        with patch.object(
            flutter_events,
            "consume_and_store_cover",
            AsyncMock(return_value=None),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(
                    flutter_events._apply_cover_change(
                        event,
                        cover_ref="forged",
                        remove_cover=False,
                        user_id=7,
                        sent_messages=[],
                        orphaned_messages=[],
                    )
                )
        self.assertEqual(ctx.exception.status_code, 400)


class SubmitEventCoverTest(unittest.TestCase):
    def _payload(self, cover_ref=None):
        return FlutterEventCreate(
            category_id=1,
            title="T",
            description="D",
            event_date=date(2099, 1, 1),
            event_time="10:00",
            event_end_time="11:00",
            location="Room 1",
            organizer_name="Org",
            it_equipment=None,
            materials=None,
            registration_url=None,
            cover_ref=cover_ref,
            client_request_id="request_1234567890",
        )

    def _session(self):
        session = AsyncMock()
        session.add = lambda *a, **k: None
        session.scalar = AsyncMock(return_value=None)
        return session

    def test_valid_cover_ref_stored_as_file_id_not_filename(self):
        user = SimpleNamespace(id=7)
        session = self._session()
        captured = {}

        async def _fake_create(session, creator, event_data):
            captured.update(event_data)
            return SimpleNamespace(id=55)

        with (
            patch.object(
                flutter_events,
                "get_category_by_id",
                AsyncMock(return_value=SimpleNamespace(id=1)),
            ),
            patch.object(
                flutter_events,
                "acquire_event_submission_lock",
                AsyncMock(),
            ),
            patch.object(
                flutter_events,
                "get_event_by_client_request_id",
                AsyncMock(return_value=None),
            ),
            patch.object(flutter_events, "check_rate_limit", AsyncMock()),
            patch.object(
                flutter_events,
                "find_event_schedule_conflict",
                AsyncMock(return_value=None),
            ),
            patch.object(
                flutter_events,
                "consume_and_store_cover",
                AsyncMock(return_value="MINTED_FILE_ID"),
            ),
            patch.object(
                flutter_events, "create_pending_event", side_effect=_fake_create
            ),
            patch.object(
                flutter_events,
                "get_event_by_id",
                AsyncMock(return_value=SimpleNamespace(id=55)),
            ),
            patch.object(flutter_events, "_serialize_event", return_value="SERIALIZED"),
        ):
            result = _run(
                flutter_events.submit_event(self._payload("tok"), user, session)
            )

        self.assertEqual(result, "SERIALIZED")
        # only telegram file ids are persisted
        self.assertEqual(captured["poster_file_id"], "MINTED_FILE_ID")

    def test_commit_failure_deletes_orphaned_cover(self):
        # if the DB commit fails after the cover was sent to Telegram, the image
        # must be deleted from the storage channel rather than left orphaned.
        user = SimpleNamespace(id=7)
        session = self._session()
        session.commit = AsyncMock(side_effect=RuntimeError("db down"))

        async def _fake_consume(cover_ref, user_id, *, sent_messages=None):
            if sent_messages is not None:
                sent_messages.append(999)
            return "FID"

        with (
            patch.object(
                flutter_events,
                "get_category_by_id",
                AsyncMock(return_value=SimpleNamespace(id=1)),
            ),
            patch.object(
                flutter_events,
                "acquire_event_submission_lock",
                AsyncMock(),
            ),
            patch.object(
                flutter_events,
                "get_event_by_client_request_id",
                AsyncMock(return_value=None),
            ),
            patch.object(flutter_events, "check_rate_limit", AsyncMock()),
            patch.object(
                flutter_events,
                "find_event_schedule_conflict",
                AsyncMock(return_value=None),
            ),
            patch.object(
                flutter_events, "consume_and_store_cover", side_effect=_fake_consume
            ),
            patch.object(
                flutter_events,
                "create_pending_event",
                AsyncMock(return_value=SimpleNamespace(id=55)),
            ),
            patch.object(
                flutter_events, "delete_stored_cover_message", AsyncMock()
            ) as delete_orphan,
        ):
            with self.assertRaises(RuntimeError):
                _run(flutter_events.submit_event(self._payload("tok"), user, session))
        delete_orphan.assert_awaited_once_with(999)

    def test_forged_cover_ref_fails_create_400(self):
        user = SimpleNamespace(id=7)
        session = self._session()
        with (
            patch.object(
                flutter_events,
                "get_category_by_id",
                AsyncMock(return_value=SimpleNamespace(id=1)),
            ),
            patch.object(
                flutter_events,
                "acquire_event_submission_lock",
                AsyncMock(),
            ),
            patch.object(
                flutter_events,
                "get_event_by_client_request_id",
                AsyncMock(return_value=None),
            ),
            patch.object(flutter_events, "check_rate_limit", AsyncMock()),
            patch.object(
                flutter_events,
                "find_event_schedule_conflict",
                AsyncMock(return_value=None),
            ),
            patch.object(
                flutter_events,
                "consume_and_store_cover",
                AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(
                    flutter_events.submit_event(self._payload("forged"), user, session)
                )
        self.assertEqual(ctx.exception.status_code, 400)


class CoverUrlSerializationTest(unittest.TestCase):
    def test_cover_url_present_only_with_poster(self):
        with_poster = SimpleNamespace(public_token="tok-1", poster_file_id="fid")
        without = SimpleNamespace(public_token="tok-2", poster_file_id=None)
        self.assertEqual(
            flutter_events._cover_url(with_poster), "/api/events/tok-1/cover"
        )
        self.assertIsNone(flutter_events._cover_url(without))


class BotCoverStepDisabledTest(unittest.TestCase):
    def test_prompt_poster_is_inert_while_disabled(self):
        import app.handlers.event_submission as es

        message = SimpleNamespace(answer=AsyncMock())
        state = AsyncMock()
        bot = AsyncMock()

        with (
            patch.object(
                es,
                "get_settings",
                return_value=SimpleNamespace(bot_poster_upload_enabled=False),
            ),
            patch.object(es, "prompt_registration_link", AsyncMock()) as nxt,
        ):
            _run(es.prompt_poster(message, state, bot))

        nxt.assert_awaited_once()
        message.answer.assert_not_called()
        state.update_data.assert_awaited_with(poster_file_id=None)


if __name__ == "__main__":
    unittest.main()
