from datetime import date, time
from types import SimpleNamespace
import unittest

from app.services.event_cards import format_event_card_text, render_dashboard_event_line


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

        self.assertIn("15:30", line)
        self.assertIn("Hackathon", line)
        self.assertIn("https://t.me/events_bot/events?startapp=event_", line)
        self.assertNotIn("Description", line)


if __name__ == "__main__":
    unittest.main()
