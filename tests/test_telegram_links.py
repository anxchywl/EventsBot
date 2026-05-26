import unittest

from app.services.telegram_links import (
    build_bot_start_link,
    build_event_deep_link,
    build_message_link,
    build_public_miniapp_event_url,
    build_telegram_miniapp_direct_link,
)


class TelegramLinksTest(unittest.TestCase):
    def test_public_chat_message_link_uses_username(self):
        self.assertEqual(
            build_message_link(
                telegram_chat_id=-1001234567890,
                message_id=42,
                username="@events_group",
                chat_type="supergroup",
            ),
            "https://t.me/events_group/42",
        )

    def test_private_supergroup_message_link_uses_internal_chat_id(self):
        self.assertEqual(
            build_message_link(
                telegram_chat_id=-1001234567890,
                message_id=42,
                chat_type="supergroup",
            ),
            "https://t.me/c/1234567890/42",
        )

    def test_regular_private_group_has_no_supported_message_link(self):
        self.assertIsNone(
            build_message_link(
                telegram_chat_id=-123456789,
                message_id=42,
                chat_type="group",
            )
        )

    def test_bot_start_link_normalizes_username(self):
        self.assertEqual(
            build_bot_start_link(bot_username="@events_bot", payload="event_42"),
            "https://t.me/events_bot?start=event_42",
        )

    def test_event_deep_link_uses_public_token(self):
        self.assertEqual(
            build_event_deep_link(
                bot_username="events_bot",
                public_token="123e4567-e89b-12d3-a456-426614174000",
            ),
            "https://t.me/events_bot?start=event_123e4567-e89b-12d3-a456-426614174000",
        )

    def test_public_miniapp_url_rejects_localhost(self):
        self.assertIsNone(
            build_public_miniapp_event_url(
                miniapp_base_url="http://localhost:8000",
                public_token="abc",
            )
        )

    def test_public_miniapp_url_requires_https(self):
        self.assertEqual(
            build_public_miniapp_event_url(
                miniapp_base_url="https://events.example.com",
                public_token="abc",
            ),
            "https://events.example.com/events/abc",
        )

    def test_telegram_miniapp_direct_link_uses_startapp(self):
        self.assertEqual(
            build_telegram_miniapp_direct_link(
                bot_username="@events_bot",
                miniapp_short_name="@events",
                public_token="abc",
            ),
            "https://t.me/events_bot/events?startapp=event_abc",
        )


if __name__ == "__main__":
    unittest.main()
