from datetime import UTC, datetime, timedelta
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import EventStatus, ReminderStatus, ReminderType
from app.models.event import Event
from app.models.favorite import Favorite
from app.models.reminder import Reminder
from app.models.user import User


# toggles an event in the user's favorites
async def toggle_favorite(session: AsyncSession, user: User, event_id: int) -> bool:
    """toggles favorite status. returns true if added, false if removed."""
    stmt = select(Favorite).where(
        Favorite.user_id == user.id, Favorite.event_id == event_id
    )
    result = await session.execute(stmt)
    favorite = result.scalar_one_or_none()

    # remove existing favorite or add a new one
    if favorite:
        await session.delete(favorite)
        return False
    else:
        new_fav = Favorite(user_id=user.id, event_id=event_id)
        session.add(new_fav)
        return True


# loads events favorited by a user
async def get_user_favorites(session: AsyncSession, user: User) -> Sequence[Event]:
    stmt = (
        select(Event)
        .join(Favorite, Favorite.event_id == Event.id)
        .where(
            Favorite.user_id == user.id,
            Event.status == EventStatus.APPROVED.value,
        )
        .order_by(Event.event_date, Event.event_time)
        .options(selectinload(Event.detail_messages))
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# schedules a reminder before an event
async def schedule_reminder(
    session: AsyncSession, user: User, event: Event, reminder_type: ReminderType
) -> str:
    """schedules a reminder. returns a status message string."""
    from zoneinfo import ZoneInfo
    from app.config import get_settings

    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)

    event_dt = datetime.combine(event.event_date, event.event_time).replace(tzinfo=tz)

    offset_minutes = 1440 if reminder_type == ReminderType.ONE_DAY else 60
    remind_at = event_dt - timedelta(minutes=offset_minutes)

    if remind_at <= datetime.now(tz):
        return "It's too late to set this reminder!"

    stmt = select(Reminder).where(
        Reminder.user_id == user.id,
        Reminder.event_id == event.id,
        Reminder.offset_minutes == offset_minutes,
        Reminder.status == ReminderStatus.SCHEDULED.value,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return "You already have this reminder set."

    # persist the new reminder
    reminder = Reminder(
        user_id=user.id,
        event_id=event.id,
        reminder_type=reminder_type.value,
        offset_minutes=offset_minutes,
        remind_at=remind_at.astimezone(UTC),
        status=ReminderStatus.SCHEDULED.value,
    )
    session.add(reminder)
    return f"Reminder set for {'1 day' if reminder_type == ReminderType.ONE_DAY else '1 hour'} before the event."


# max 99 days, 23 hours, 59 minutes = 143_999 minutes
MAX_OFFSET_MINUTES = 143_999
MAX_REMINDERS_PER_EVENT = 3


def validate_reminder_offset(offset_minutes: int) -> None:
    if offset_minutes <= 0:
        raise ValueError("Reminder must be greater than 0 minutes.")
    if offset_minutes > MAX_OFFSET_MINUTES:
        raise ValueError("Reminder cannot be more than 99 days before the event.")


async def schedule_reminder_offset(
    session: AsyncSession,
    user: User,
    event: Event,
    offset_minutes: int,
) -> Reminder:
    from zoneinfo import ZoneInfo
    from app.config import get_settings

    validate_reminder_offset(offset_minutes)

    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    event_dt = datetime.combine(event.event_date, event.event_time).replace(tzinfo=tz)
    remind_at = event_dt - timedelta(minutes=offset_minutes)

    if remind_at <= datetime.now(tz):
        raise ValueError("It's too late to set this reminder.")

    result = await session.execute(
        select(Reminder)
        .where(
            Reminder.user_id == user.id,
            Reminder.event_id == event.id,
            Reminder.offset_minutes == offset_minutes,
        )
        .order_by(Reminder.id.desc())
    )
    existing = result.scalars().first()
    if existing:
        existing.reminder_type = f"offset_{offset_minutes}"
        existing.remind_at = remind_at.astimezone(UTC)
        existing.status = ReminderStatus.SCHEDULED.value
        existing.sent_at = None
        await session.flush()
        return existing

    count_result = await session.execute(
        select(Reminder.id).where(
            Reminder.user_id == user.id,
            Reminder.event_id == event.id,
            Reminder.status == ReminderStatus.SCHEDULED.value,
        )
    )
    if len(count_result.scalars().all()) >= MAX_REMINDERS_PER_EVENT:
        raise ValueError("Reminder limit reached.")

    reminder = Reminder(
        user_id=user.id,
        event_id=event.id,
        reminder_type=f"offset_{offset_minutes}",
        offset_minutes=offset_minutes,
        remind_at=remind_at.astimezone(UTC),
        status=ReminderStatus.SCHEDULED.value,
    )
    session.add(reminder)
    await session.flush()
    return reminder


async def cancel_reminder(
    session: AsyncSession,
    user: User,
    reminder_id: int,
) -> int | None:
    result = await session.execute(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user.id,
            Reminder.status == ReminderStatus.SCHEDULED.value,
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return None
    event_id = reminder.event_id
    await session.delete(reminder)
    return event_id


async def get_user_scheduled_reminders(
    session: AsyncSession,
    user: User,
    limit: int,
    offset: int,
) -> Sequence[Reminder]:
    result = await session.execute(
        select(Reminder)
        .where(
            Reminder.user_id == user.id,
            Reminder.status == ReminderStatus.SCHEDULED.value,
        )
        .join(Reminder.event)
        .where(Event.status == EventStatus.APPROVED.value)
        .order_by(Reminder.remind_at)
        .options(selectinload(Reminder.event).selectinload(Event.category))
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


# loads reminders due for delivery
async def get_due_reminders(session: AsyncSession) -> Sequence[Reminder]:
    now = datetime.now(UTC)
    stmt = (
        select(Reminder)
        .where(
            Reminder.status == ReminderStatus.SCHEDULED.value,
            Reminder.remind_at <= now,
        )
        .join(Reminder.event)
        .where(Event.status == EventStatus.APPROVED.value)
        .options(selectinload(Reminder.user), selectinload(Reminder.event))
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# marks one reminder as sent
async def mark_reminder_sent(session: AsyncSession, reminder_id: int) -> None:
    stmt = select(Reminder).where(Reminder.id == reminder_id)
    result = await session.execute(stmt)
    reminder = result.scalar_one_or_none()
    # update only when the reminder still exists
    if reminder:
        reminder.status = ReminderStatus.SENT.value
        reminder.sent_at = datetime.now(UTC)
