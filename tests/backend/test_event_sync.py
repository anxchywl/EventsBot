from datetime import date, time
from types import SimpleNamespace
import unittest

import pytest

from app.models.enums import EventStatus
from app.services import dashboard_bus
from app.services.dashboard_bus import DashboardBus
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


def test_dashboard_bus_requires_initialization(monkeypatch):
    monkeypatch.setattr(dashboard_bus, "_bus", None)

    with pytest.raises(RuntimeError):
        dashboard_bus.get_bus()


def test_init_bus_registers_global_instance(monkeypatch):
    monkeypatch.setattr(dashboard_bus, "_bus", None)
    bot = object()
    session_factory = object()

    bus = dashboard_bus.init_bus(bot, session_factory)

    assert dashboard_bus.get_bus() is bus


def test_dashboard_bus_schedule_refresh_ignores_empty_batches():
    bus = DashboardBus(bot=object(), session_factory=object())

    bus.schedule_refresh(set())

    assert bus._queue.qsize() == 0


def test_dashboard_bus_schedule_refresh_enqueues_chat_ids():
    bus = DashboardBus(bot=object(), session_factory=object())

    bus.schedule_refresh({1, 2})

    assert bus._queue.qsize() == 1
    assert bus._queue.get_nowait() == {1, 2}


if __name__ == "__main__":
    unittest.main()
