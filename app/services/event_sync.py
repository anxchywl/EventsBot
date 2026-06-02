from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import Chat, ChatCategorySetting
from app.models.enums import EventStatus
from app.models.event import Event, EventDetailMessage
from app.models.event_sync import EventSyncJob
from app.services.chats import delete_chat_by_id
from app.services.event_cards import build_event_page_keyboard, format_event_card_text
from app.services.telegram_delivery import (
    call_with_telegram_backoff,
    is_bot_removed_error,
    pause_between_telegram_deliveries,
)
from app.services.telegram_links import build_message_link

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import async_sessionmaker


logger = logging.getLogger(__name__)

EVENT_SYNC_NOTIFY_CHANNEL = "event_sync_changed"
DELETE_LIKE_OPERATIONS = {"rejected", "needs_changes", "cancelled", "archived", "deleted"}
VISIBLE_STATUSES = {EventStatus.APPROVED.value}
MAX_ATTEMPTS = 5
POLL_SECONDS = 5.0


class EventSyncDeliveryError(RuntimeError):
    pass


def asyncpg_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def acquire_event_lock(session: AsyncSession, event_id: int) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": int(event_id)})


async def capture_event_snapshot(
    session: AsyncSession,
    event_id: int,
) -> dict[str, Any]:
    result = await session.execute(
        select(Event)
        .where(Event.id == event_id)
        .options(
            selectinload(Event.detail_messages).selectinload(EventDetailMessage.chat)
        )
        .execution_options(populate_existing=True)
    )
    event = result.scalar_one_or_none()
    if event is None:
        return {"event_id": event_id, "event_exists": False, "detail_messages": []}

    return {
        "event_id": event.id,
        "event_exists": True,
        "status": event.status,
        "category_id": event.category_id,
        "detail_messages": [
            {
                "chat_id": detail.chat_id,
                "telegram_chat_id": detail.chat.telegram_chat_id if detail.chat else None,
                "chat_type": detail.chat.chat_type if detail.chat else None,
                "chat_username": detail.chat.username if detail.chat else None,
                "message_id": detail.message_id,
            }
            for detail in event.detail_messages
        ],
    }


async def enqueue_event_sync(
    session: AsyncSession,
    *,
    event_id: int | None,
    operation: str,
    snapshot: dict[str, Any] | None = None,
) -> EventSyncJob:
    payload = {"snapshot": snapshot or {}, "operation": operation}
    job = EventSyncJob(
        event_id=event_id,
        operation=operation,
        payload_json=payload,
    )
    session.add(job)
    await session.flush()
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {
            "channel": EVENT_SYNC_NOTIFY_CHANNEL,
            "payload": json.dumps({"job_id": job.id, "event_id": event_id, "operation": operation}),
        },
    )
    logger.info("queued event sync job %s for event %s operation=%s", job.id, event_id, operation)
    return job


async def latest_completed_sync_version(session: AsyncSession) -> dict[str, Any]:
    row = (
        await session.execute(
            select(func.max(EventSyncJob.id), func.max(EventSyncJob.processed_at)).where(
                EventSyncJob.status == "completed"
            )
        )
    ).one()
    version, completed_at = row
    return {
        "version": int(version or 0),
        "completed_at": completed_at.isoformat() if completed_at else None,
    }


async def listen_for_event_sync_notifications(
    database_url: str,
    callback,
) -> None:
    import asyncpg

    connection = None
    while True:
        try:
            connection = await asyncpg.connect(asyncpg_database_url(database_url))

            def _listener(_connection, _pid, _channel, payload) -> None:
                callback(payload)

            await connection.add_listener(EVENT_SYNC_NOTIFY_CHANNEL, _listener)
            logger.info("listening for event sync notifications")
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            if connection is not None:
                await connection.close()
            raise
        except Exception as exc:
            logger.warning("event sync notification listener failed: %s", exc)
            if connection is not None:
                await connection.close()
                connection = None
            await asyncio.sleep(3)


class EventSyncWorker:
    def __init__(self, bot: "Bot", session_factory: "async_sessionmaker") -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._event_locks: dict[int, asyncio.Lock] = {}

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="event_sync_worker")
        self._task.add_done_callback(self._log_task_result)

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    def wakeup(self) -> None:
        self._wakeup.set()

    def _log_task_result(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "event sync worker stopped unexpectedly: %s",
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    async def _run(self) -> None:
        await self._reset_stale_processing_jobs()
        while True:
            try:
                await self._process_pending_jobs()
                self._wakeup.clear()
                try:
                    await asyncio.wait_for(self._wakeup.wait(), timeout=POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("event sync worker error: %s", exc)
                await asyncio.sleep(1)

    async def _reset_stale_processing_jobs(self) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                update(EventSyncJob)
                .where(EventSyncJob.status == "processing")
                .values(status="pending", last_error="Reset after worker startup")
                .returning(EventSyncJob.id)
            )
            job_ids = list(result.scalars().all())
            if job_ids:
                logger.warning("reset %d stale processing event sync jobs", len(job_ids))
            await session.commit()

    async def _process_pending_jobs(self) -> None:
        while True:
            async with self._session_factory() as session:
                job = await _claim_next_job(session)
                if job is None:
                    return
                await session.commit()

            event_lock_id = job.event_id or int((job.payload_json or {}).get("snapshot", {}).get("event_id") or 0)
            lock = self._event_locks.setdefault(event_lock_id, asyncio.Lock())
            async with lock:
                await self._process_job_id(job.id)

    async def _process_job_id(self, job_id: int) -> None:
        async with self._session_factory() as session:
            job = await session.get(EventSyncJob, job_id)
            if job is None:
                return
            logger.info("event sync job %s started event=%s operation=%s", job.id, job.event_id, job.operation)
            try:
                await self._apply_job(session, job)
            except Exception as exc:
                await _mark_job_failed(session, job, exc)
                await session.commit()
                return

            job.status = "completed"
            job.processed_at = datetime.now(UTC)
            job.last_error = None
            await session.flush()
            await _notify_sync_completed(session, job)
            await session.commit()
            logger.info("event sync job %s completed", job.id)

    async def _apply_job(self, session: AsyncSession, job: EventSyncJob) -> None:
        snapshot = ((job.payload_json or {}).get("snapshot") or {})
        operation = job.operation
        event_id = job.event_id or snapshot.get("event_id")

        event = None
        if event_id is not None:
            event = await session.get(
                Event,
                int(event_id),
                options=[selectinload(Event.category), selectinload(Event.detail_messages)],
            )

        old_chat_ids = _snapshot_chat_ids(snapshot)
        if event is None or operation in DELETE_LIKE_OPERATIONS or event.status not in VISIBLE_STATUSES:
            await self._delete_snapshot_detail_messages(session, snapshot)
            if event_id is not None:
                await session.execute(delete(EventDetailMessage).where(EventDetailMessage.event_id == int(event_id)))
            await session.flush()
            await _schedule_dashboard_refresh(old_chat_ids)
            return

        new_chats = await _matching_chats(session, event)
        new_chat_ids = {chat.id for chat in new_chats}
        affected_chat_ids = old_chat_ids | new_chat_ids

        current_details = await _detail_messages_by_chat(session, event.id)
        obsolete_chat_ids = set(current_details) - new_chat_ids
        for chat_id in obsolete_chat_ids:
            detail = current_details[chat_id]
            await _delete_detail_message(self._bot, detail)
            await session.delete(detail)
            logger.info("deleted obsolete detail message event=%s chat=%s", event.id, chat_id)

        bot_user = await self._bot.get_me()
        delivery_failures: list[str] = []
        for chat in new_chats:
            detail = current_details.get(chat.id)
            if detail is None:
                detail = EventDetailMessage(event_id=event.id, chat_id=chat.id, message_id=0)
                session.add(detail)
                await session.flush()
            try:
                await _upsert_detail_message(self._bot, event, chat, detail, bot_user.username)
            except Exception as exc:
                if is_bot_removed_error(exc):
                    await delete_chat_by_id(session, chat.id)
                    logger.warning("removed chat %s after sync delivery failed: %s", chat.telegram_chat_id, exc)
                    continue
                logger.warning("failed to sync detail message event=%s chat=%s: %s", event.id, chat.id, exc)
                delivery_failures.append(f"chat {chat.id}: {exc}")
                if not detail.message_id:
                    await session.delete(detail)
                continue
            if not detail.message_id:
                delivery_failures.append(f"chat {chat.id}: missing Telegram message id after delivery")
                await session.delete(detail)
                continue
            affected_chat_ids.add(chat.id)
            await pause_between_telegram_deliveries()

        await session.flush()
        await _schedule_dashboard_refresh(affected_chat_ids)
        if delivery_failures:
            raise EventSyncDeliveryError("; ".join(delivery_failures))

    async def _delete_snapshot_detail_messages(
        self,
        session: AsyncSession,
        snapshot: dict[str, Any],
    ) -> None:
        for item in snapshot.get("detail_messages") or []:
            telegram_chat_id = item.get("telegram_chat_id")
            message_id = item.get("message_id")
            chat_id = item.get("chat_id")
            if not telegram_chat_id or not message_id:
                continue
            try:
                await call_with_telegram_backoff(
                    lambda: self._bot.delete_message(
                        chat_id=telegram_chat_id,
                        message_id=message_id,
                    ),
                    context=f"delete event detail in chat {telegram_chat_id}",
                )
                logger.info("deleted detail message chat=%s message=%s", telegram_chat_id, message_id)
            except Exception as exc:
                if chat_id and is_bot_removed_error(exc):
                    await delete_chat_by_id(session, int(chat_id))
                    logger.warning("removed chat %s after delete failed: %s", telegram_chat_id, exc)
                    continue
                logger.warning("failed to delete detail message chat=%s message=%s: %s", telegram_chat_id, message_id, exc)


async def _claim_next_job(session: AsyncSession) -> EventSyncJob | None:
    result = await session.execute(
        select(EventSyncJob)
        .where(
            EventSyncJob.status.in_(["pending", "failed"]),
            EventSyncJob.attempts < MAX_ATTEMPTS,
        )
        .order_by(EventSyncJob.created_at, EventSyncJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None
    job.status = "processing"
    job.attempts += 1
    await session.flush()
    return job


async def _mark_job_failed(session: AsyncSession, job: EventSyncJob, exc: Exception) -> None:
    job.status = "failed"
    job.last_error = str(exc)
    logger.exception("event sync job %s failed: %s", job.id, exc)
    await session.flush()


async def _notify_sync_completed(session: AsyncSession, job: EventSyncJob) -> None:
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {
            "channel": EVENT_SYNC_NOTIFY_CHANNEL,
            "payload": json.dumps({"job_id": job.id, "event_id": job.event_id, "status": "completed"}),
        },
    )


def _snapshot_chat_ids(snapshot: dict[str, Any]) -> set[int]:
    return {
        int(item["chat_id"])
        for item in snapshot.get("detail_messages") or []
        if item.get("chat_id") is not None
    }


async def _matching_chats(session: AsyncSession, event: Event) -> list[Chat]:
    result = await session.execute(
        select(Chat)
        .join(ChatCategorySetting, ChatCategorySetting.chat_id == Chat.id)
        .where(
            ChatCategorySetting.category_id == event.category_id,
            ChatCategorySetting.is_enabled.is_(True),
            Chat.is_active.is_(True),
            Chat.chat_type != "private",
            Chat.categories_selected.is_(True),
        )
    )
    return list(result.scalars().all())


async def _detail_messages_by_chat(session: AsyncSession, event_id: int) -> dict[int, EventDetailMessage]:
    result = await session.execute(
        select(EventDetailMessage)
        .where(EventDetailMessage.event_id == event_id)
        .options(selectinload(EventDetailMessage.chat))
    )
    return {detail.chat_id: detail for detail in result.scalars().all()}


async def _delete_detail_message(bot: "Bot", detail: EventDetailMessage) -> None:
    if not detail.chat:
        return
    try:
        await call_with_telegram_backoff(
            lambda: bot.delete_message(
                chat_id=detail.chat.telegram_chat_id,
                message_id=detail.message_id,
            ),
            context=f"delete obsolete event detail in chat {detail.chat.telegram_chat_id}",
        )
    except Exception as exc:
        logger.warning(
            "failed to delete obsolete detail event=%s chat=%s message=%s: %s",
            detail.event_id,
            detail.chat_id,
            detail.message_id,
            exc,
        )


async def _upsert_detail_message(
    bot: "Bot",
    event: Event,
    chat: Chat,
    detail: EventDetailMessage,
    bot_username: str | None,
) -> None:
    text_body = format_event_card_text(event, caption_safe=bool(event.poster_file_id))
    keyboard = build_event_page_keyboard(
        event,
        bot_username=bot_username,
        use_web_app=False,
        open_event_only=True,
    )

    if detail.message_id:
        try:
            if event.poster_file_id:
                await call_with_telegram_backoff(
                    lambda: bot.edit_message_caption(
                        chat_id=chat.telegram_chat_id,
                        message_id=detail.message_id,
                        caption=text_body,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    ),
                    context=f"edit event {event.id} caption in chat {chat.telegram_chat_id}",
                )
            else:
                await call_with_telegram_backoff(
                    lambda: bot.edit_message_text(
                        chat_id=chat.telegram_chat_id,
                        message_id=detail.message_id,
                        text=text_body,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    ),
                    context=f"edit event {event.id} text in chat {chat.telegram_chat_id}",
                )
            detail.message_link = build_message_link(
                telegram_chat_id=chat.telegram_chat_id,
                message_id=detail.message_id,
                username=chat.username,
                chat_type=chat.chat_type,
            )
            logger.info("updated detail message event=%s chat=%s", event.id, chat.id)
            return
        except TelegramBadRequest as exc:
            message = str(exc).lower()
            if "message is not modified" in message:
                return
            logger.warning(
                "detail message edit failed event=%s chat=%s; recreating: %s",
                event.id,
                chat.id,
                exc,
            )
            try:
                await bot.delete_message(
                    chat_id=chat.telegram_chat_id,
                    message_id=detail.message_id,
                )
            except Exception:
                pass

    if event.poster_file_id:
        sent = await call_with_telegram_backoff(
            lambda: bot.send_photo(
                chat_id=chat.telegram_chat_id,
                photo=event.poster_file_id,
                caption=text_body,
                reply_markup=keyboard,
                parse_mode="HTML",
            ),
            context=f"send event {event.id} photo to chat {chat.telegram_chat_id}",
        )
    else:
        sent = await call_with_telegram_backoff(
            lambda: bot.send_message(
                chat_id=chat.telegram_chat_id,
                text=text_body,
                reply_markup=keyboard,
                parse_mode="HTML",
            ),
            context=f"send event {event.id} text to chat {chat.telegram_chat_id}",
        )

    detail.message_id = sent.message_id
    detail.message_link = build_message_link(
        telegram_chat_id=chat.telegram_chat_id,
        message_id=sent.message_id,
        username=chat.username,
        chat_type=chat.chat_type,
    )
    logger.info("created detail message event=%s chat=%s message=%s", event.id, chat.id, sent.message_id)


async def _schedule_dashboard_refresh(chat_ids: set[int]) -> None:
    if not chat_ids:
        return
    try:
        from app.services.dashboard_bus import get_bus

        get_bus().schedule_refresh(chat_ids)
        logger.info("scheduled dashboard refresh for %d chats", len(chat_ids))
    except Exception as exc:
        logger.warning("failed to schedule dashboard refresh: %s", exc)
