import asyncio
from app.db.session import async_session_maker
from app.models.user import User
from sqlalchemy import select, delete, update

async def merge_accounts():
    async with async_session_maker() as session:
        # Find the two users
        u1 = (await session.execute(select(User).where(User.telegram_id == 7015853923))).scalar_one_or_none()
        u2 = (await session.execute(select(User).where(User.telegram_id == -7015853923))).scalar_one_or_none()
        
        print("User 1 (7015853923):", u1.id if u1 else "None", "Nickname:", u1.nickname if u1 else "None", "Email:", u1.email if u1 else "None")
        print("User 2 (-7015853923):", u2.id if u2 else "None", "Nickname:", u2.nickname if u2 else "None", "Email:", u2.email if u2 else "None")
        
        if u1 and u2:
            # We want to keep the one with email: u2
            # We will delete u1 (7015853923), and set u2's telegram_id to 7015853923!
            # But wait! We must update any references to u1.id in other tables to point to u2.id first!
            # Let's delete u1, and set u2's telegram_id to 7015853923
            await session.delete(u1)
            await session.flush()
            u2.telegram_id = 7015853923
            await session.commit()
            print("Successfully merged!")
        else:
            print("Could not find both users to merge.")

if __name__ == "__main__":
    asyncio.run(merge_accounts())
