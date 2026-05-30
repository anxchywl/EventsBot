import asyncio
from sqlalchemy import select, update
from app.db.session import async_session_maker
from app.models.event import Event
from app.models.user import User

async def main():
    async with async_session_maker() as session:
        # Find user emka
        result = await session.execute(select(User).where(User.telegram_id == 7015853923))
        emka = result.scalar_one_or_none()
        
        if not emka:
            print("User emka not found in DB!")
            return
            
        print(f"Found emka with DB ID: {emka.id}")
        
        # Update events creator to emka's ID
        stmt = update(Event).where(Event.creator_user_id == 1).values(creator_user_id=emka.id)
        await session.execute(stmt)
        await session.commit()
        print("Reassigned all events from user ID 1 to emka successfully!")

if __name__ == "__main__":
    asyncio.run(main())
