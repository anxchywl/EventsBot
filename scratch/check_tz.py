import asyncio
from app.db.session import async_session_maker
from app.models.event import Event
from sqlalchemy import select, func, String, TIMESTAMP, cast, text
from datetime import timedelta

async def main():
    async with async_session_maker() as session:
        # Check current UTC time from DB
        utc_now = (await session.execute(select(func.timezone("UTC", func.now())))).scalar()
        print("DB UTC now:", utc_now)
        
        res = await session.execute(select(Event))
        events = res.scalars().all()
        for e in events:
            # Let's run the exact timezone logic
            event_start_utc_stmt = select(
                func.timezone(
                    "UTC", 
                    func.timezone(
                        e.timezone, 
                        cast(cast(e.event_date, String) + ' ' + cast(e.event_time, String), TIMESTAMP)
                    )
                )
            )
            event_start_utc = (await session.execute(event_start_utc_stmt)).scalar()
            diff = event_start_utc + timedelta(hours=2) - utc_now
            is_active = (event_start_utc + timedelta(hours=2)) >= utc_now
            print(f"Event: {e.title}")
            print(f"  Date/Time: {e.event_date} {e.event_time} ({e.timezone})")
            print(f"  Calculated UTC start: {event_start_utc}")
            print(f"  Start + 2 hrs: {event_start_utc + timedelta(hours=2)}")
            print(f"  Diff to UTC now: {diff}")
            print(f"  Is Active (starts + 2h >= now): {is_active}")

if __name__ == "__main__":
    asyncio.run(main())
