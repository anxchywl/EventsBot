import os

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.models.enums import EventStatus  # noqa: E402
from app.models.event_sync import EventSyncJob  # noqa: E402
from app.services.event_sync import (  # noqa: E402
    _claim_next_job,
    capture_event_snapshot,
    enqueue_event_sync,
    latest_completed_sync_version,
)


@pytest.mark.anyio
async def test_enqueue_writes_job_row_and_fires_pg_notify(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        event = await make_event(
            session, creator, category, status=EventStatus.APPROVED.value
        )

        job = await enqueue_event_sync(
            session, event_id=event.id, operation="approved", snapshot={}
        )

        assert job.id is not None
        stored = await session.get(EventSyncJob, job.id)
        assert stored.operation == "approved"
        assert stored.status == "pending"


@pytest.mark.anyio
async def test_claim_next_job_marks_processing_and_increments_attempts(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        event = await make_event(
            session, creator, category, status=EventStatus.APPROVED.value
        )
        await enqueue_event_sync(
            session, event_id=event.id, operation="approved", snapshot={}
        )

        claimed = await _claim_next_job(session)
        assert claimed is not None
        assert claimed.status == "processing"
        assert claimed.attempts == 1

        assert await _claim_next_job(session) is None


@pytest.mark.anyio
async def test_capture_snapshot_reads_real_event(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        event = await make_event(
            session, creator, category, status=EventStatus.APPROVED.value
        )

        snapshot = await capture_event_snapshot(session, event.id)
        assert snapshot["event_exists"] is True
        assert snapshot["status"] == EventStatus.APPROVED.value
        assert snapshot["category_id"] == category.id
        assert snapshot["detail_messages"] == []


@pytest.mark.anyio
async def test_capture_snapshot_for_missing_event(db_session):
    async with db_session() as session:
        snapshot = await capture_event_snapshot(session, 987654)
        assert snapshot["event_exists"] is False


@pytest.mark.anyio
async def test_latest_completed_version_tracks_max_completed_job(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        event = await make_event(
            session, creator, category, status=EventStatus.APPROVED.value
        )

        assert (await latest_completed_sync_version(session))["version"] == 0

        job = await enqueue_event_sync(
            session, event_id=event.id, operation="approved", snapshot={}
        )
        from datetime import UTC, datetime

        job.status = "completed"
        job.processed_at = datetime.now(UTC)
        await session.flush()

        version = await latest_completed_sync_version(session)
        assert version["version"] == job.id
        assert version["completed_at"] is not None


@pytest.mark.anyio
async def test_pending_and_failed_jobs_are_claimable_but_exhausted_are_not(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        event = await make_event(
            session, creator, category, status=EventStatus.APPROVED.value
        )
        job = await enqueue_event_sync(
            session, event_id=event.id, operation="approved", snapshot={}
        )
        job.status = "failed"
        job.attempts = 5
        await session.flush()

        assert await _claim_next_job(session) is None

        remaining = (await session.execute(select(EventSyncJob.status))).scalars().all()
        assert remaining == ["failed"]
