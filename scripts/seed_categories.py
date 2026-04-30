import asyncio

from sqlalchemy import select

from app.db.session import async_session_maker
from app.models.event import EventCategory


async def seed_categories():
    categories = [
        {"name": "Computer Science", "slug": "computer_science"},
        {"name": "Business", "slug": "business"},
        {"name": "Engineering", "slug": "engineering"},
        {"name": "Design", "slug": "design"},
        {"name": "Career", "slug": "career"},
        {"name": "Hackathons", "slug": "hackathons"},
        {"name": "Workshops", "slug": "workshops"},
        {"name": "Sport", "slug": "sport"},
        {"name": "Volunteering", "slug": "volunteering"},
        {"name": "Entertainment", "slug": "entertainment"},
        {"name": "Club Events", "slug": "club_events"},
    ]

    async with async_session_maker() as session:
        for i, cat_data in enumerate(categories):
            # check by both name and slug to be safe
            stmt = select(EventCategory).where(
                (EventCategory.slug == cat_data["slug"])
                | (EventCategory.name == cat_data["name"])
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if not existing:
                new_cat = EventCategory(
                    name=cat_data["name"],
                    slug=cat_data["slug"],
                    sort_order=i * 10,
                )
                session.add(new_cat)
                # commit after each to avoid autoflush issues in the next iteration
                await session.commit()
            else:
                # refresh session state
                await session.rollback()

        print("Categories sync completed.")


if __name__ == "__main__":
    asyncio.run(seed_categories())
