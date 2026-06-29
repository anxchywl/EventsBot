import asyncio
import json
import os
import unittest
from urllib.parse import urlsplit

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("MINIAPP_SESSION_TTL_SECONDS", "86400")

from app.web.main import web_app  # noqa: E402
from app.web.realtime import publish_review_deleted, subscribe_miniapp_events  # noqa: E402


async def _asgi_request(
    method: str,
    target: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    sent: list[dict] = []
    parsed = urlsplit(target)
    raw_headers = [
        (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
    ]
    if body:
        raw_headers.append((b"content-length", str(len(body)).encode()))
        raw_headers.append((b"content-type", b"application/json"))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": parsed.path,
        "raw_path": parsed.path.encode(),
        "query_string": parsed.query.encode(),
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await web_app(scope, receive, send)
    status_code = next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return status_code, response_body


class FastAPIEndpointSecurityTest(unittest.TestCase):
    def test_friends_endpoints_reject_missing_session(self):
        for path in (
            "/api/friends",
            "/api/friends/requests",
            "/api/friends/events/1/friends-going",
        ):
            status_code, _body = asyncio.run(_asgi_request("GET", path))
            self.assertEqual(status_code, 401, path)

    def test_reminders_endpoints_reject_missing_session(self):
        for method, path, body in (
            ("GET", "/api/reminders", b""),
            (
                "POST",
                "/api/events/event_123e4567-e89b-12d3-a456-426614174000/reminders",
                json.dumps({"offset_minutes": 30}).encode(),
            ),
        ):
            status_code, _body = asyncio.run(_asgi_request(method, path, body=body))
            self.assertEqual(status_code, 401, path)

    def test_favorites_endpoints_reject_missing_session(self):
        for method, path in (
            ("GET", "/api/favorites"),
            ("POST", "/api/events/event_123e4567-e89b-12d3-a456-426614174000/favorite"),
        ):
            status_code, _body = asyncio.run(_asgi_request(method, path))
            self.assertEqual(status_code, 401, path)

    def test_review_write_endpoints_reject_missing_session(self):
        status_code, _body = asyncio.run(
            _asgi_request(
                "POST",
                "/api/events/event_123e4567-e89b-12d3-a456-426614174000/reviews",
                body=json.dumps({"score": 5, "content": "Good"}).encode(),
            )
        )
        self.assertEqual(status_code, 401)

    def test_admin_endpoints_reject_missing_session(self):
        for path in (
            "/api/admin/users",
            "/api/admin/audit-logs",
            "/api/admin/connected-groups",
        ):
            status_code, _body = asyncio.run(_asgi_request("GET", path))
            self.assertEqual(status_code, 401, path)

    def test_public_event_sort_values_are_whitelisted(self):
        status_code, _body = asyncio.run(
            _asgi_request("GET", "/api/events?sort=created_at")
        )
        self.assertEqual(status_code, 422)

    def test_public_review_token_is_validated_before_lookup(self):
        status_code, _body = asyncio.run(
            _asgi_request("GET", "/api/events/not-a-token/reviews")
        )
        self.assertEqual(status_code, 404)

    def test_sse_update_token_is_required_and_bounded(self):
        status_code, _body = asyncio.run(_asgi_request("GET", "/api/events/updates"))
        self.assertEqual(status_code, 422)

        too_long = "a" * 4097
        status_code, _body = asyncio.run(
            _asgi_request("GET", f"/api/events/updates?token={too_long}")
        )
        self.assertEqual(status_code, 422)

    def test_review_deleted_realtime_event_does_not_expose_internal_ids(self):
        async def run_check():
            stream = subscribe_miniapp_events()
            pending = asyncio.create_task(anext(stream))
            await asyncio.sleep(0)
            await publish_review_deleted(
                {
                    "deleted": True,
                    "event_id": 10,
                    "event_token": "event_123e4567-e89b-12d3-a456-426614174000",
                    "target_user_id": 20,
                    "rating_ids": [30],
                    "comment_ids": [40],
                    "average_rating": 4.5,
                    "rating_count": 2,
                    "rating_distribution": {"5": 1},
                    "review_count": 1,
                    "deleted_at": "2026-06-07T00:00:00+00:00",
                }
            )
            message = await asyncio.wait_for(pending, timeout=1)
            await stream.aclose()
            return message

        message = asyncio.run(run_check())
        self.assertEqual(message["type"], "review_deleted")
        self.assertEqual(
            message["event_token"], "event_123e4567-e89b-12d3-a456-426614174000"
        )
        self.assertNotIn("event_id", message)
        self.assertNotIn("target_user_id", message)
        self.assertNotIn("rating_ids", message)
        self.assertNotIn("comment_ids", message)


if __name__ == "__main__":
    unittest.main()
