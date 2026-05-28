import asyncio
from app.db.session import async_session_maker
from app.models.event import Event
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        res = await session.execute(select(Event))
        events = res.scalars().all()
        print("Total events in DB:", len(events))
        for e in events:
            print(f"- Title: {e.title}, Status: {e.status}, Date: {e.event_date}, Time: {e.event_time}")

if __name__ == "__main__":
    asyncio.run(main())
