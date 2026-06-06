import asyncio
from app.db.session import get_session
from app.models.event import Event
from app.models.user import User
from sqlalchemy import select
from app.services.friends import bulk_event_friends_going

async def test():
    # Setup session
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.session import engine
    
    async with AsyncSession(engine) as session:
        # find the user by email or get the first user
        users = await session.execute(select(User))
        for u in users.scalars().all():
            print(f"User: {u.id} - {u.email} - verified: {u.is_verified}")
            
        # Get an event
        events = await session.execute(select(Event).limit(5))
        for e in events.scalars().all():
            print(f"Event: {e.id} - {e.title}")
            
        # Check friends for user 1 and event 1
        user = await session.scalar(select(User).where(User.id == 1))
        if user:
            res = await bulk_event_friends_going(session, user, [1])
            print(f"Friends going: {res}")

if __name__ == "__main__":
    asyncio.run(test())
