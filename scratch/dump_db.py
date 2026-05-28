import asyncio
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.event import Event

async def main():
    async with async_session_maker() as session:
        result = await session.execute(select(Event))
        events = result.scalars().all()
        print(f"Total events found: {len(events)}")
        for event in events:
            print(f"ID: {event.id}")
            print(f"  Title: {event.title}")
            print(f"  Status: {event.status}")
            print(f"  Date: {event.event_date} Time: {event.event_time}")
            print(f"  Creator: {event.creator_user_id}")
            print(f"  Category: {event.category_id}")
            print(f"  Poster ID: {event.poster_file_id}")
            print(f"  Public Token: {event.public_token}")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
