from datetime import date, time
from types import SimpleNamespace

import pytest

from app.models.enums import ReminderStatus
from app.models.event import Event
from app.models.reminder import Reminder
from app.models.user import User
from app.services.reminders import schedule_reminder_offset


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def first(self):
        return self.values[0] if self.values else None

    def all(self):
        return self.values


class FakeExecuteResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return FakeScalarResult(self.values)


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.flushed = 0

    async def execute(self, _stmt):
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushed += 1


@pytest.fixture(autouse=True)
def utc_settings(monkeypatch):
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(app_timezone="UTC"),
    )


def future_event() -> Event:
    return Event(id=20, event_date=date(2099, 1, 1), event_time=time(12, 0))


@pytest.mark.anyio
async def test_schedule_reminder_offset_reactivates_existing_reminder():
    existing = Reminder(
        id=1,
        user_id=10,
        event_id=20,
        offset_minutes=60,
        reminder_type="offset_60",
        status=ReminderStatus.SENT.value,
    )
    existing.sent_at = object()
    session = FakeSession([FakeExecuteResult([existing])])

    reminder = await schedule_reminder_offset(
        session,
        User(id=10),
        future_event(),
        60,
    )

    assert reminder is existing
    assert reminder.status == ReminderStatus.SCHEDULED.value
    assert reminder.sent_at is None
    assert session.added == []
    assert session.flushed == 1


@pytest.mark.anyio
async def test_schedule_reminder_offset_enforces_per_event_limit():
    session = FakeSession(
        [
            FakeExecuteResult([]),
            FakeExecuteResult([1, 2, 3]),
        ]
    )

    with pytest.raises(ValueError, match="Reminder limit reached"):
        await schedule_reminder_offset(session, User(id=10), future_event(), 30)

    assert session.added == []
    assert session.flushed == 0


@pytest.mark.anyio
async def test_schedule_reminder_offset_adds_new_reminder_under_limit():
    session = FakeSession(
        [
            FakeExecuteResult([]),
            FakeExecuteResult([1, 2]),
        ]
    )

    reminder = await schedule_reminder_offset(
        session,
        User(id=10),
        future_event(),
        30,
    )

    assert reminder.user_id == 10
    assert reminder.event_id == 20
    assert reminder.offset_minutes == 30
    assert reminder.reminder_type == "offset_30"
    assert reminder.status == ReminderStatus.SCHEDULED.value
    assert session.added == [reminder]
    assert session.flushed == 1
