from datetime import date, time
from types import SimpleNamespace
import unittest

from app.models.enums import EventStatus
from app.services.event_sync import asyncpg_database_url
from app.web.serializers import is_event_archived, is_event_ended


class EventSyncHelpersTest(unittest.TestCase):
    def test_asyncpg_database_url_removes_sqlalchemy_driver(self):
        self.assertEqual(
            "postgresql://user:pass@localhost/db",
            asyncpg_database_url("postgresql+asyncpg://user:pass@localhost/db"),
        )

    def test_manual_archived_status_is_archived(self):
        event = SimpleNamespace(
            status=EventStatus.ARCHIVED.value,
            event_date=date(2026, 12, 31),
            event_time=time(18, 30),
            timezone="Asia/Almaty",
        )

        self.assertTrue(is_event_archived(event))

    def test_past_approved_event_is_ended_but_not_manually_archived(self):
        event = SimpleNamespace(
            status=EventStatus.APPROVED.value,
            event_date=date(2020, 1, 1),
            event_time=time(18, 30),
            timezone="Asia/Almaty",
        )

        self.assertTrue(is_event_ended(event))
        self.assertFalse(is_event_archived(event))


if __name__ == "__main__":
    unittest.main()
