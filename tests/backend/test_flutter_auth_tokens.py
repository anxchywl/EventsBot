import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-bytes")

import jwt  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from app.web.flutter_auth import (  # noqa: E402
    FLUTTER_JWT_ALGORITHM,
    FLUTTER_JWT_AUDIENCE,
    FLUTTER_JWT_ISSUER,
    _flutter_jwt_secret,
    create_flutter_token,
    decode_flutter_token,
    require_flutter_admin,
    require_flutter_user,
)
from app.web.routers.flutter_auth import (  # noqa: E402
    require_native_flutter_auth,
    session_profile,
)
from app.web.superapp_bridge import decode_superapp_token  # noqa: E402


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
        forged = self._sign(self._payload(), key="different-test-secret-at-least-32b")
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


class SessionProfileTest(unittest.TestCase):
    def test_returns_server_authoritative_profile_without_echoing_token(self):
        user = SimpleNamespace(
            id=7,
            role="admin",
            first_name="Coordinator",
            is_verified=True,
        )

        profile = _run(session_profile(user=user))

        self.assertEqual(profile.user_id, 7)
        self.assertEqual(profile.role, "admin")
        self.assertEqual(profile.first_name, "Coordinator")
        self.assertTrue(profile.is_verified)
        self.assertNotIn("token", profile.model_dump())


class RequireUserTest(unittest.TestCase):
    def test_native_token_uses_database_role_not_role_claim(self):
        token = self._native_token(user_id=9, role="admin")
        user = SimpleNamespace(id=9, role="user", is_blocked=False)
        session = SimpleNamespace(get=AsyncMock(return_value=user))
        settings = self._native_settings()

        with (
            patch(
                "app.web.flutter_auth.try_superapp_user",
                AsyncMock(return_value=None),
            ),
            patch("app.web.flutter_auth.get_settings", return_value=settings),
        ):
            resolved = _run(
                require_flutter_user(
                    authorization=f"Bearer {token}",
                    session=session,
                )
            )

        self.assertIs(resolved, user)
        self.assertEqual(resolved.role, "user")

    def test_blocked_native_user_is_forbidden(self):
        token = self._native_token(user_id=9)
        user = SimpleNamespace(id=9, role="user", is_blocked=True)
        session = SimpleNamespace(get=AsyncMock(return_value=user))
        settings = self._native_settings()

        with (
            patch(
                "app.web.flutter_auth.try_superapp_user",
                AsyncMock(return_value=None),
            ),
            patch("app.web.flutter_auth.get_settings", return_value=settings),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(
                    require_flutter_user(
                        authorization=f"Bearer {token}",
                        session=session,
                    )
                )

        self.assertEqual(ctx.exception.status_code, 403)

    def _native_token(self, *, user_id: int, role: str = "user") -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "iss": FLUTTER_JWT_ISSUER,
                "aud": FLUTTER_JWT_AUDIENCE,
                "sub": str(user_id),
                "role": role,
                "iat": now,
                "exp": now + timedelta(days=1),
            },
            _flutter_jwt_secret(),
            algorithm=FLUTTER_JWT_ALGORITHM,
        )

    def _native_settings(self) -> SimpleNamespace:
        return SimpleNamespace(
            flutter_native_auth_enabled=True,
            session_secret=SecretStr(_flutter_jwt_secret()),
        )


class NativeAuthAvailabilityTest(unittest.TestCase):
    def test_native_login_is_hidden_when_disabled(self):
        with patch(
            "app.web.routers.flutter_auth.get_settings",
            return_value=SimpleNamespace(flutter_native_auth_enabled=False),
        ):
            with self.assertRaises(HTTPException) as ctx:
                require_native_flutter_auth()
        self.assertEqual(ctx.exception.status_code, 404)

    def test_native_login_can_be_enabled_for_debug_development(self):
        with patch(
            "app.web.routers.flutter_auth.get_settings",
            return_value=SimpleNamespace(flutter_native_auth_enabled=True),
        ):
            self.assertIsNone(require_native_flutter_auth())


class SuperappTokenValidationTest(unittest.TestCase):
    def _settings(self) -> SimpleNamespace:
        return SimpleNamespace(
            superapp_jwt_public_key=None,
            superapp_jwt_secret=SecretStr("s" * 32),
            superapp_jwt_algorithm="HS256",
            superapp_jwt_audience="jas-wallet",
            superapp_jwt_issuer="university-superapp",
        )

    def _token(self, **overrides) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "iss": "university-superapp",
            "aud": "jas-wallet",
            "sub": "wallet-user-17",
            "exp": now + timedelta(minutes=5),
        }
        claims.update(overrides)
        return jwt.encode(claims, "s" * 32, algorithm="HS256")

    def test_valid_superapp_token_is_verified(self):
        with patch(
            "app.web.superapp_bridge.get_settings",
            return_value=self._settings(),
        ):
            claims = decode_superapp_token(self._token())
        self.assertEqual(claims["sub"], "wallet-user-17")

    def test_wrong_superapp_issuer_is_rejected(self):
        with patch(
            "app.web.superapp_bridge.get_settings",
            return_value=self._settings(),
        ):
            with self.assertRaises(jwt.InvalidIssuerError):
                decode_superapp_token(self._token(iss="attacker"))


if __name__ == "__main__":
    unittest.main()
