import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from urllib.parse import urlencode

from fastapi import HTTPException

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("MINIAPP_SESSION_TTL_SECONDS", "86400")

from app.config import get_settings
from app.web.auth import (  # noqa: E402
    MiniAppUser,
    create_session_token,
    require_current_miniapp_user,
    verify_init_data,
    verify_session_token,
)
from app.web.main import web_app  # noqa: E402


def _signed_init_data(user_id: int, *, auth_date: int | None = None) -> str:
    get_settings.cache_clear()
    values = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAEAAAE",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Test",
                "username": f"user{user_id}",
            },
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    bot_token = get_settings().bot_token.get_secret_value()
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(values)


def _tamper_payload(token: str, **updates) -> str:
    header_part, payload_part, signature = token.split(".", 2)
    payload = json.loads(base64.urlsafe_b64decode(_pad_b64(payload_part)))
    payload.update(updates)
    tampered_payload_part = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{header_part}.{tampered_payload_part}.{signature}"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _pad_b64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode()


async def _asgi_get(path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    sent: list[dict] = []
    raw_headers = [
        (key.lower().encode(), value.encode())
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await web_app(scope, receive, send)
    status_code = next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return status_code, body


class MiniAppAuthSecurityTest(unittest.TestCase):
    def test_invalid_init_data_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            verify_init_data("auth_date=1&user=%7B%7D")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_init_data_rejected(self):
        get_settings.cache_clear()
        expired = int(time.time()) - get_settings().miniapp_session_ttl_seconds - 1
        with self.assertRaises(HTTPException) as ctx:
            verify_init_data(_signed_init_data(1001, auth_date=expired))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_tampered_init_data_rejected(self):
        init_data = _signed_init_data(1001)
        tampered = init_data.replace("user1001", "user9999")
        with self.assertRaises(HTTPException) as ctx:
            verify_init_data(tampered)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_session_token_cannot_spoof_another_user(self):
        token = create_session_token(MiniAppUser(id=1001, username="user1001"))
        tampered = _tamper_payload(token, telegram_id=2002, sub="2002")
        with self.assertRaises(HTTPException) as ctx:
            verify_session_token(tampered)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_session_rejects_mismatched_current_telegram_user(self):
        token = create_session_token(MiniAppUser(id=1001, username="user1001"))
        init_data_for_other_user = _signed_init_data(2002)

        async def run_check():
            return await require_current_miniapp_user(
                authorization=f"Bearer {token}",
                x_telegram_init_data=init_data_for_other_user,
            )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(run_check())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_protected_endpoint_rejects_missing_session(self):
        status_code, _body = asyncio.run(_asgi_get("/api/favorites"))
        self.assertEqual(status_code, 401)

    def test_protected_endpoint_rejects_invalid_session(self):
        status_code, _body = asyncio.run(
            _asgi_get(
                "/api/favorites",
                headers={"Authorization": "Bearer not-a-valid-token"},
            )
        )
        self.assertEqual(status_code, 401)


if __name__ == "__main__":
    unittest.main()
