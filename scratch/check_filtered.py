import asyncio
from app.db.session import async_session_maker
from app.models.event import Event
from app.models.user import User
from app.web.routers.events import _filtered_events
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        # Get first user
        user_res = await session.execute(select(User).where(User.is_verified == True))
        user = user_res.scalars().first()
        print("Verified User in DB:", user.nickname if user else None)
        
        events_guest = await _filtered_events(
            session,
            sort="time_asc",
            relevance="active",
            categories=[],
            organizers=[],
            locations=[],
            favorite_only=False,
            user=None
        )
        print("Events for Guest:", [e.title for e in events_guest])
        
        if user:
            events_user = await _filtered_events(
                session,
                sort="time_asc",
                relevance="active",
                categories=[],
                organizers=[],
                locations=[],
                favorite_only=False,
                user=user
            )
            print("Events for User:", [e.title for e in events_user])

if __name__ == "__main__":
    asyncio.run(main())
