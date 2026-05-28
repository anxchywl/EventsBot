import asyncio
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.event import EventCategory

async def main():
    async with async_session_maker() as session:
        result = await session.execute(select(EventCategory))
        categories = result.scalars().all()
        print(f"Total categories found: {len(categories)}")
        for cat in categories:
            print(f"ID: {cat.id} | Name: {cat.name} | Slug: {cat.slug} | Active: {cat.is_active}")

if __name__ == "__main__":
    asyncio.run(main())
