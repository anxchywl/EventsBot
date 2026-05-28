import asyncio
from app.db.session import async_session_maker
from app.services.events import get_available_event_by_public_token

async def main():
    async with async_session_maker() as session:
        # HackNU26 token is 2f5d6dea-245c-40f1-b9bb-3b4a47ef7a57
        token = "2f5d6dea-245c-40f1-b9bb-3b4a47ef7a57"
        event = await get_available_event_by_public_token(session, token)
        if event:
            print(f"Success! Found past approved event: {event.title}")
            print(f"Status: {event.status}")
            print(f"Date: {event.event_date}")
        else:
            print("Failure: Past approved event not found.")

if __name__ == "__main__":
    asyncio.run(main())
