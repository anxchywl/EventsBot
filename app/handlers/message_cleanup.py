from __future__ import annotations

import asyncio
from collections.abc import Iterable


async def delete_messages_fast(
    bot,
    chat_id: int,
    message_ids: Iterable[int | None],
    *,
    batch_size: int = 100,
) -> None:
    unique_ids = list(dict.fromkeys(msg_id for msg_id in message_ids if msg_id))
    for index in range(0, len(unique_ids), batch_size):
        batch = unique_ids[index : index + batch_size]
        if hasattr(bot, "delete_messages"):
            try:
                await bot.delete_messages(chat_id=chat_id, message_ids=batch)
                continue
            except Exception:
                pass

        await asyncio.gather(
            *(
                bot.delete_message(chat_id=chat_id, message_id=message_id)
                for message_id in batch
            ),
            return_exceptions=True,
        )
