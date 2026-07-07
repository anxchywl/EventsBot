import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from app.services.analytics_dashboard import _resolve_avatar_url  # noqa: E402


class ResolveAvatarUrlTest(unittest.TestCase):
    def test_stored_photo_url_wins(self):
        self.assertEqual(
            _resolve_avatar_url("https://cdn/pic.jpg", 123, None),
            "https://cdn/pic.jpg",
        )

    def test_falls_back_to_proxy_keyed_by_telegram_id(self):
        url = _resolve_avatar_url(None, 555, None)
        self.assertTrue(url.startswith("/api/events/avatar/555?"))
        # without a photo timestamp the version defaults to the telegram id
        self.assertIn("v=555", url)

    def test_proxy_version_uses_photo_timestamp_when_present(self):
        ts = datetime(2026, 3, 1, 9, 30, tzinfo=timezone.utc)
        url = _resolve_avatar_url(None, 555, ts)
        # a changed photo timestamp busts the cached avatar
        self.assertIn("2026-03-01", url)

    def test_no_photo_and_no_valid_telegram_id_returns_none(self):
        self.assertIsNone(_resolve_avatar_url(None, 0, None))
        self.assertIsNone(_resolve_avatar_url(None, None, None))


if __name__ == "__main__":
    unittest.main()
