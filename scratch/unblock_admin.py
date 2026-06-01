import asyncio
from app.db.session import async_session_maker
from app.models.user import User
from sqlalchemy import update

async def unblock_admin():
    async with async_session_maker() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == 7015853923)
            .values(is_blocked=False, blocked_reason=None, blocked_at=None, blocked_by_admin_id=None)
        )
        await session.commit()
    print("Admin unblocked successfully!")

if __name__ == "__main__":
    asyncio.run(unblock_admin())
