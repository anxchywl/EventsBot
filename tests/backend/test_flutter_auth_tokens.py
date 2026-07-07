import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

import jwt  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.web.flutter_auth import (  # noqa: E402
    FLUTTER_JWT_ALGORITHM,
    FLUTTER_JWT_AUDIENCE,
    FLUTTER_JWT_ISSUER,
    _flutter_jwt_secret,
    create_flutter_token,
    decode_flutter_token,
    require_flutter_admin,
)


def _run(coro):
    return asyncio.run(coro)


class TokenRoundtripTest(unittest.TestCase):
    def test_admin_user_encodes_admin_role(self):
        token = create_flutter_token(SimpleNamespace(id=1, role="admin"))
        payload = decode_flutter_token(token)
        self.assertEqual(payload["sub"], "1")
        self.assertEqual(payload["role"], "admin")

    def test_non_admin_roles_downgraded_to_user(self):
        # any legacy/unknown role must never sign as admin
        for role in ("user", "moderator", "superuser", None):
            token = create_flutter_token(SimpleNamespace(id=2, role=role))
            self.assertEqual(decode_flutter_token(token)["role"], "user")


class TokenValidationTest(unittest.TestCase):
    def _payload(self, **overrides):
        now = datetime.now(timezone.utc)
        payload = {
            "iss": FLUTTER_JWT_ISSUER,
            "aud": FLUTTER_JWT_AUDIENCE,
            "sub": "5",
            "role": "user",
            "iat": now,
            "exp": now + timedelta(days=1),
        }
        payload.update(overrides)
        return payload

    def _sign(self, payload, key=None):
        return jwt.encode(
            payload, key or _flutter_jwt_secret(), algorithm=FLUTTER_JWT_ALGORITHM
        )

    def test_tampered_signature_rejected(self):
        forged = self._sign(self._payload(), key="a-different-secret")
        with self.assertRaises(jwt.InvalidTokenError):
            decode_flutter_token(forged)

    def test_expired_token_rejected(self):
        expired = self._sign(
            self._payload(exp=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_flutter_token(expired)

    def test_wrong_issuer_rejected(self):
        wrong = self._sign(self._payload(iss="some-other-issuer"))
        with self.assertRaises(jwt.InvalidIssuerError):
            decode_flutter_token(wrong)

    def test_wrong_audience_rejected(self):
        wrong = self._sign(self._payload(aud="some-other-audience"))
        with self.assertRaises(jwt.InvalidAudienceError):
            decode_flutter_token(wrong)

    def test_garbage_token_rejected(self):
        with self.assertRaises(jwt.InvalidTokenError):
            decode_flutter_token("not.a.jwt")


class RequireAdminTest(unittest.TestCase):
    def test_non_admin_forbidden(self):
        with self.assertRaises(HTTPException) as ctx:
            _run(require_flutter_admin(user=SimpleNamespace(role="user")))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_admin_allowed(self):
        admin = SimpleNamespace(role="admin")
        self.assertIs(_run(require_flutter_admin(user=admin)), admin)


if __name__ == "__main__":
    unittest.main()
