import asyncio
from sqlalchemy import select, String, Interval, TIMESTAMP, func
from datetime import timedelta
from app.db.session import async_session_maker
from app.models.event import Event
from app.web.routers.events import _filtered_events

async def main():
    async with async_session_maker() as session:
        # Check active events
        active = await _filtered_events(session, sort="time_asc", relevance="active", categories=[], organizers=[], locations=[], favorite_only=False, user=None)
        print("Active events in Python query:")
        for e in active:
            print(f" - {e.title} (date: {e.event_date}, time: {e.event_time}, timezone: {e.timezone})")
            
        # Check archived events
        archived = await _filtered_events(session, sort="time_asc", relevance="archived", categories=[], organizers=[], locations=[], favorite_only=False, user=None)
        print("Archived events in Python query:")
        for e in archived:
            print(f" - {e.title} (date: {e.event_date}, time: {e.event_time}, timezone: {e.timezone})")

        # Let's inspect the raw timezone values from postgres
        stmt = select(
            Event.title,
            Event.event_date,
            Event.event_time,
            Event.timezone,
            func.timezone("UTC", func.now()).label("now_utc"),
            func.timezone(
                "UTC", 
                func.timezone(
                    Event.timezone, 
                    func.cast(func.cast(Event.event_date, String) + ' ' + func.cast(Event.event_time, String), TIMESTAMP)
                )
            ).label("start_utc")
        )
        res = await session.execute(stmt)
        print("\nRaw database values and computed UTC start:")
        for row in res.all():
            print(f"Title: {row.title}")
            print(f"  Date/Time: {row.event_date} {row.event_time}")
            print(f"  Event TZ: {row.timezone}")
            print(f"  Computed Start UTC: {row.start_utc}")
            print(f"  Now UTC: {row.now_utc}")
            if row.start_utc:
                print(f"  Start UTC + 2h: {row.start_utc + timedelta(hours=2)}")
                print(f"  Is Active (start + 2h >= now): {row.start_utc + timedelta(hours=2) >= row.now_utc}")
            print("-" * 30)

if __name__ == "__main__":
    asyncio.run(main())
