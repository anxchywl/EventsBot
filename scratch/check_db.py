import asyncio
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.event import Event
from app.models.user import User

async def main():
    async with async_session_maker() as session:
        # Check users
        users_result = await session.execute(select(User))
        users = users_result.scalars().all()
        print("--- USERS ---")
        for u in users:
            print(f"ID: {u.id}, Telegram ID: {u.telegram_id}, Name: {u.first_name}, Username: {u.username}")
        
        # Check events
        events_result = await session.execute(select(Event))
        events = events_result.scalars().all()
        print("\n--- EVENTS ---")
        for e in events:
            print(f"ID: {e.id}, Creator User ID: {e.creator_user_id}, Title: {e.title}, Status: {e.status}, Parent Event ID: {e.parent_event_id}")

if __name__ == "__main__":
    asyncio.run(main())
