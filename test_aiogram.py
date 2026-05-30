import asyncio
from aiogram.filters import Filter
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

class AdminModQueueFilter(Filter):
    async def __call__(self, message: Message, state: FSMContext) -> bool | dict[str, any]:
        data = await state.get_data()
        if data.get("admin_mod_queue_mode") is True:
            event_map = data.get("admin_mod_queue_map")
            if event_map and message.text in event_map:
                return {"event_id": event_map[message.text]}
        return False
