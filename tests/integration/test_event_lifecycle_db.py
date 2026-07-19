import os
from datetime import date, time

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.models.enums import EventStatus, ModerationAction  # noqa: E402
from app.models.event import Event  # noqa: E402
from app.models.event_sync import EventSyncJob  # noqa: E402
from app.models.moderation import ModerationLog  # noqa: E402
from app.services.events import (  # noqa: E402
    delete_event_completely,
    find_event_schedule_conflict,
    get_category_by_id,
    get_event_by_public_token,
    get_pending_events,
    update_event_status,
)


@pytest.mark.anyio
async def test_create_pending_event_persists_row_and_submission_log(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        user = await make_user(session)
        category = await make_category(session)
        event = await make_event(session, user, category)

        assert event.id is not None
        assert event.status == EventStatus.PENDING.value
        assert event.public_token  # minted

        actions = (
            (
                await session.execute(
                    select(ModerationLog.action).where(
                        ModerationLog.event_id == event.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert actions == [ModerationAction.SUBMITTED.value]


@pytest.mark.anyio
async def test_approve_persists_status_and_metadata(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session, telegram_id=1)
        admin = await make_user(session, telegram_id=2, role="admin")
        category = await make_category(session)
        event = await make_event(session, creator, category)

        updated = await update_event_status(
            session, event.id, EventStatus.APPROVED, admin, "looks good"
        )

        assert updated.status == EventStatus.APPROVED.value
        assert updated.approved_by_user_id == admin.id
        assert updated.approved_at is not None
        assert updated.moderation_note == "looks good"

        fresh = await session.get(Event, event.id)
        assert fresh.status == EventStatus.APPROVED.value


@pytest.mark.anyio
async def test_restore_from_archived_records_restored_action(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session, telegram_id=1)
        admin = await make_user(session, telegram_id=2, role="admin")
        category = await make_category(session)
        event = await make_event(
            session, creator, category, status=EventStatus.ARCHIVED.value
        )

        updated = await update_event_status(
            session, event.id, EventStatus.APPROVED, admin
        )

        assert updated.status == EventStatus.APPROVED.value
        assert updated.restored_at is not None
        last_action = (
            await session.execute(
                select(ModerationLog.action)
                .where(ModerationLog.event_id == event.id)
                .order_by(ModerationLog.id.desc())
                .limit(1)
            )
        ).scalar_one()
        assert last_action == ModerationAction.RESTORED.value


@pytest.mark.anyio
async def test_get_pending_events_dedupes_drafts_and_orders_queue(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)

        parent = await make_event(
            session,
            creator,
            category,
            status=EventStatus.APPROVED.value,
            title="Parent",
        )
        await make_event(
            session, creator, category, title="Old draft", parent_event_id=parent.id
        )
        newest = await make_event(
            session, creator, category, title="New draft", parent_event_id=parent.id
        )
        resubmitted = await make_event(
            session, creator, category, status=EventStatus.RESUBMITTED.value, title="Re"
        )

        pending = await get_pending_events(session)
        ids = [e.id for e in pending]

        assert parent.id not in ids
        assert newest.id in ids
        assert ids.index(resubmitted.id) < ids.index(newest.id)


@pytest.mark.anyio
async def test_get_event_by_public_token_normalizes_prefix(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        event = await make_event(session, creator, category)

        found = await get_event_by_public_token(session, f"event_{event.public_token}")
        assert found is not None
        assert found.id == event.id


@pytest.mark.anyio
async def test_delete_event_completely_removes_row_and_enqueues_cleanup(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        event = await make_event(
            session, creator, category, status=EventStatus.APPROVED.value
        )
        event_id = event.id

        deleted = await delete_event_completely(session, bot=None, event_id=event_id)
        assert deleted is True

        assert await session.get(Event, event_id) is None

        job_ops = (
            (
                await session.execute(
                    select(EventSyncJob.operation).where(
                        EventSyncJob.event_id == event_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "deleted" in job_ops

        # sanity: deleting a non-existent event is a no-op returning False
        assert (
            await delete_event_completely(session, bot=None, event_id=999999) is False
        )


@pytest.mark.anyio
async def test_status_check_constraint_rejects_invalid_status(
    db_session, make_user, make_category, make_event
):
    from sqlalchemy.exc import IntegrityError

    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        event = await make_event(session, creator, category)

        event.status = "not_a_real_status"
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.anyio
async def test_public_token_unique_index_enforced(
    db_session, make_user, make_category, make_event
):
    from sqlalchemy.exc import IntegrityError

    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        first = await make_event(session, creator, category)

        dup = await make_event(session, creator, category, title="Dup")
        dup.public_token = first.public_token
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.anyio
async def test_client_request_id_unique_index_enforced(
    db_session, make_user, make_category, make_event
):
    from sqlalchemy.exc import IntegrityError

    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        await make_event(
            session,
            creator,
            category,
            client_request_id="request_1234567890",
            client_request_fingerprint="a" * 64,
        )

        with pytest.raises(IntegrityError):
            await make_event(
                session,
                creator,
                category,
                title="Duplicate request",
                client_request_id="request_1234567890",
                client_request_fingerprint="a" * 64,
            )


@pytest.mark.anyio
async def test_schedule_conflict_uses_time_overlap_not_the_whole_day(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        existing = await make_event(session, creator, category)

        overlap = await find_event_schedule_conflict(
            session,
            event_date=date(2099, 5, 1),
            event_time=time(19, 0),
            event_end_time=time(21, 0),
            location="  block   c  ",
        )
        adjacent = await find_event_schedule_conflict(
            session,
            event_date=date(2099, 5, 1),
            event_time=time(20, 0),
            event_end_time=time(21, 0),
            location="Block C",
        )

        assert overlap.id == existing.id
        assert adjacent is None


@pytest.mark.anyio
async def test_inactive_category_cannot_be_selected(db_session, make_category):
    async with db_session() as session:
        category = await make_category(session, is_active=False)
        assert await get_category_by_id(session, category.id) is None
