"""
dashboard_bus.py — central event-driven dashboard refresh bus.

responsibilities:
  - accept refresh signals from handlers/services (non-blocking)
  - debounce rapid signals per chat (2-second window)
  - run refreshes in isolated db sessions to avoid request-session leaks
  - recreate missing dashboard messages automatically
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

logger = logging.getLogger(__name__)

# debounce window: refreshes that arrive within this many seconds are coalesced
_DEBOUNCE_SECONDS = 2.0


class DashboardBus:
    """
    singleton-style bus that collects chat ids and refreshes their dashboards
    in a background worker with debouncing.
    """

    def __init__(self, bot: "Bot", session_factory: "async_sessionmaker") -> None:
        self._bot = bot
        self._session_factory = session_factory
        # pending chat ids that need a refresh (internal db id, not telegram id)
        self._pending: set[int] = set()
        self._queue: asyncio.Queue[set[int]] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # public api
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """launch the background worker. call once at bot startup."""
        self._task = asyncio.create_task(self._worker(), name="dashboard_bus_worker")

    def stop(self) -> None:
        """cancel the background worker. call at bot shutdown."""
        if self._task:
            self._task.cancel()

    def schedule_refresh(self, chat_ids: set[int]) -> None:
        """
        non-blocking. enqueue chat ids for a debounced dashboard refresh.
        chat_ids are internal db ids (chat.id), not telegram ids.
        """
        if not chat_ids:
            return
        # put onto the queue so the worker can pick it up
        self._queue.put_nowait(chat_ids)

    # ------------------------------------------------------------------ #
    # internal worker
    # ------------------------------------------------------------------ #

    async def _worker(self) -> None:
        """
        drains the queue with debouncing. waits _DEBOUNCE_SECONDS after the
        last signal before firing, coalescing all chat ids that arrived.
        """
        pending: set[int] = set()
        while True:
            try:
                # block until first item arrives
                batch = await self._queue.get()
                pending.update(batch)

                # drain any further items that arrive within the debounce window
                while True:
                    try:
                        batch = await asyncio.wait_for(
                            self._queue.get(), timeout=_DEBOUNCE_SECONDS
                        )
                        pending.update(batch)
                    except asyncio.TimeoutError:
                        break

                # fire refreshes for all coalesced chat ids
                if pending:
                    to_refresh = pending.copy()
                    pending.clear()
                    await self._refresh_chats(to_refresh)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("dashboard_bus worker error: %s", exc)
                await asyncio.sleep(1)

    async def _refresh_chats(self, chat_ids: set[int]) -> None:
        """opens a fresh db session and updates dashboards for each chat."""
        from app.models.chat import Chat, DashboardMessage
        from app.services.dashboard import create_or_update_dashboard_message
        from sqlalchemy import select

        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(Chat).where(Chat.id.in_(chat_ids), Chat.is_active.is_(True))
                )
                chats = result.scalars().all()

                for chat in chats:
                    try:
                        await create_or_update_dashboard_message(
                            session=session,
                            bot=self._bot,
                            chat=chat,
                        )
                        await session.commit()
                    except Exception as exc:
                        logger.warning(
                            "failed to refresh dashboard for chat %s: %s",
                            chat.telegram_chat_id,
                            exc,
                        )
                        await session.rollback()
            except Exception as exc:
                logger.exception("dashboard_bus refresh session error: %s", exc)


# module-level singleton, populated at startup
_bus: DashboardBus | None = None


def get_bus() -> DashboardBus:
    if _bus is None:
        raise RuntimeError("DashboardBus not initialized. Call init_bus() at startup.")
    return _bus


def init_bus(bot: "Bot", session_factory: "async_sessionmaker") -> DashboardBus:
    """create and register the global bus. call once from main()."""
    global _bus
    _bus = DashboardBus(bot=bot, session_factory=session_factory)
    return _bus


async def get_chat_ids_for_event(session: "AsyncSession", event_id: int) -> set[int]:
    """
    returns the internal db chat ids where a given event has been published
    (i.e. it has an EventDetailMessage). used to target refresh signals precisely.
    """
    from app.models.event import EventDetailMessage
    from sqlalchemy import select

    result = await session.execute(
        select(EventDetailMessage.chat_id).where(
            EventDetailMessage.event_id == event_id
        )
    )
    return set(result.scalars().all())


async def get_all_active_dashboard_chat_ids(session: "AsyncSession") -> set[int]:
    """
    returns internal db chat ids of all chats that have a dashboard message.
    used by the periodic sweep to keep every dashboard up to date.
    """
    from app.models.chat import DashboardMessage
    from sqlalchemy import select

    result = await session.execute(select(DashboardMessage.chat_id))
    return set(result.scalars().all())
