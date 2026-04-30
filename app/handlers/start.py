from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Hello. I am the Student Events bot.\n\n"
        "Stage 1 is running: bot startup and /start are configured.\n"
        "Event submission, moderation, and dashboards will be added in later stages."
    )
