import unittest

import pytest

from app.config import Settings


# pydantic-settings matches init kwargs by their env-var alias, so the superapp
# fields must be passed by their SUPERAPP_* alias names here
def _settings(**overrides):
    base = {"BOT_TOKEN": "123456:test-token"}
    base.update(overrides)
    return Settings(**base)


class SuperappHmacSecretGuardTest(unittest.TestCase):
    """Regression: when the superapp bridge is enabled with a symmetric HS*
    algorithm, a short shared secret is brute-forceable, so boot must fail.
    The default (disabled / asymmetric) posture must stay unaffected."""

    def test_short_hs_secret_is_rejected_when_bridge_enabled(self):
        with pytest.raises(ValueError, match="at least 32 bytes"):
            _settings(
                SUPERAPP_JWT_ISSUER="superapp",
                SUPERAPP_JWT_ALGORITHM="HS256",
                SUPERAPP_JWT_SECRET="tooshort",
            )

    def test_long_hs_secret_is_accepted(self):
        settings = _settings(
            SUPERAPP_JWT_ISSUER="superapp",
            SUPERAPP_JWT_ALGORITHM="HS256",
            SUPERAPP_JWT_SECRET="x" * 32,
        )
        self.assertTrue(settings.superapp_bridge_enabled)

    def test_disabled_bridge_ignores_short_secret(self):
        # no issuer -> bridge inert -> secret length is irrelevant
        settings = _settings(
            SUPERAPP_JWT_ALGORITHM="HS256",
            SUPERAPP_JWT_SECRET="short",
        )
        self.assertFalse(settings.superapp_bridge_enabled)

    def test_asymmetric_algorithm_is_not_subject_to_hmac_length_rule(self):
        # RS256 uses a PEM public key, not a shared secret, so the length guard
        # does not apply
        settings = _settings(
            SUPERAPP_JWT_ISSUER="superapp",
            SUPERAPP_JWT_ALGORITHM="RS256",
            SUPERAPP_JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nabc\n-----END-----",
        )
        self.assertTrue(settings.superapp_bridge_enabled)


class FlutterDevelopmentGuardTest(unittest.TestCase):
    def test_native_auth_is_disabled_by_default(self):
        self.assertFalse(_settings().flutter_native_auth_enabled)

    def test_native_auth_requires_debug_runtime(self):
        with pytest.raises(ValueError, match="development access"):
            _settings(FLUTTER_NATIVE_AUTH_ENABLED=True, LOG_LEVEL="INFO")

    def test_native_auth_can_be_enabled_for_development(self):
        settings = _settings(
            FLUTTER_NATIVE_AUTH_ENABLED=True,
            LOG_LEVEL="DEBUG",
        )
        self.assertTrue(settings.flutter_native_auth_enabled)


if __name__ == "__main__":
    unittest.main()
