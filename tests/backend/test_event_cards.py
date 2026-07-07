from datetime import date, time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services.event_cards import (
    build_event_page_keyboard,
    format_event_card_text,
    render_dashboard_event_line,
)
from app.services.publisher import get_event_detail_keyboard
from app.handlers.admin_panel import _render_admin_moderation_event_text
from app.services.event_cards import escape_and_fit_description


class EventCardsTest(unittest.TestCase):
    def test_event_card_escapes_user_content_and_includes_fields(self):
        event = SimpleNamespace(
            title="<Hackathon>",
            description="Build <fast>",
            event_date=date(2026, 5, 25),
            event_time=time(15, 30),
            location="Main <Hall>",
            organizer_name="CS & AI",
            category=SimpleNamespace(name="Computer Science"),
        )

        text = format_event_card_text(event)

        self.assertIn("&lt;Hackathon&gt;", text)
        self.assertIn("Build &lt;fast&gt;", text)
        self.assertIn("May 25, 2026", text)
        self.assertIn("15:30", text)
        self.assertIn("Main &lt;Hall&gt;", text)
        self.assertIn("CS &amp; AI", text)
        self.assertIn("Computer Science", text)

    def test_dashboard_line_is_short_and_uses_deep_link(self):
        event = SimpleNamespace(
            title="Hackathon",
            event_date=date(2026, 5, 25),
            event_time=time(15, 30),
            location="Main Hall",
            public_token="123e4567-e89b-12d3-a456-426614174000",
        )

        line = render_dashboard_event_line(
            event,
            bot_username="events_bot",
            include_date=False,
        )

        self.assertIn("<b>15:30</b>", line)
        self.assertIn("Hackathon", line)
        self.assertIn("https://t.me/events_bot/events?startapp=event_", line)
        self.assertNotIn("Description", line)

    def test_dashboard_line_italicizes_date_and_time_when_included(self):
        event = SimpleNamespace(
            title="Hackathon",
            event_date=date(2026, 12, 31),
            event_time=time(18, 30),
            location="Main Hall",
            public_token="123e4567-e89b-12d3-a456-426614174000",
        )

        line = render_dashboard_event_line(
            event,
            bot_username="events_bot",
            include_date=True,
        )

        self.assertIn("<b>Dec 31 18:30</b>", line)

    def test_event_card_caption_safe_text_fits_telegram_photo_limit(self):
        event = SimpleNamespace(
            title="Hackathon",
            description="Long description " * 120,
            event_date=date(2026, 5, 25),
            event_time=time(15, 30),
            location="Main Hall",
            organizer_name="CS Club",
            category=SimpleNamespace(name="Computer Science"),
        )

        text = format_event_card_text(event, caption_safe=True)

        self.assertLessEqual(len(text), 1024)
        self.assertIn("...", text)

    def test_group_publish_keyboard_has_only_url_open_event(self):
        event = SimpleNamespace(
            public_token="abc123",
            registration_url="https://registration.example.com",
        )

        with patch(
            "app.services.event_cards.get_settings",
            return_value=SimpleNamespace(
                miniapp_base_url="https://events.example.com",
                telegram_miniapp_short_name="events",
            ),
        ):
            markup = get_event_detail_keyboard(event, bot_username="events_bot")

        buttons = [button for row in markup.inline_keyboard for button in row]
        self.assertEqual(1, len(buttons))
        self.assertEqual("Open in App", buttons[0].text)
        self.assertIsNone(buttons[0].web_app)
        self.assertEqual(
            "https://t.me/events_bot/events?startapp=event_abc123&mode=compact",
            buttons[0].url,
        )

    def test_event_keyboard_falls_back_to_public_miniapp_url(self):
        event = SimpleNamespace(public_token="abc123")

        with patch(
            "app.services.event_cards.get_settings",
            return_value=SimpleNamespace(
                miniapp_base_url="https://events.example.com",
                telegram_miniapp_short_name="events",
            ),
        ):
            markup = build_event_page_keyboard(event)

        buttons = [button for row in markup.inline_keyboard for button in row]
        self.assertEqual(1, len(buttons))
        self.assertEqual("Open in App", buttons[0].text)
        self.assertEqual("https://events.example.com/events/abc123", buttons[0].url)

    def test_admin_moderation_caption_keeps_poster_with_long_description(self):
        event = SimpleNamespace(
            title="Hackathon",
            description="Long moderation description " * 120,
            event_date=date(2026, 5, 25),
            event_time=time(15, 30),
            location="Main Hall",
            status="pending",
        )

        def render_text(safe_desc):
            return _render_admin_moderation_event_text(
                event,
                safe_title="Hackathon",
                safe_creator="Admin (@admin)",
                safe_location="Main Hall",
                safe_cat="Computer Science",
                safe_desc=safe_desc,
                safe_registration="None",
            )

        text = render_text(escape_and_fit_description(event.description, render_text))

        self.assertLessEqual(len(text), 1024)
        self.assertIn("...", text)
        self.assertIn("Description:", text)


if __name__ == "__main__":
    unittest.main()
