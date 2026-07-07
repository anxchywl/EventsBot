import os

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import pytest  # noqa: E402

from app.models.enums import EventStatus  # noqa: E402
from app.models.rating import Rating  # noqa: E402
from app.services.analytics_dashboard import AnalyticsFilters, compute_summary  # noqa: E402
from app.services.favorites import (  # noqa: E402
    add_favorite,
    get_favorite_event_ids,
    is_event_favorite,
    remove_favorite,
)
from app.web.serializers import rating_summaries  # noqa: E402


@pytest.mark.anyio
async def test_favorite_add_is_idempotent_and_removable(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        user = await make_user(session)
        category = await make_category(session)
        event = await make_event(
            session, user, category, status=EventStatus.APPROVED.value
        )

        assert await add_favorite(session, user, event) is True
        assert await add_favorite(session, user, event) is False
        assert await is_event_favorite(session, user, event.id) is True
        assert await get_favorite_event_ids(session, user, [event.id]) == {event.id}

        assert await remove_favorite(session, user, event) is True
        # removing again reports nothing was deleted
        assert await remove_favorite(session, user, event) is False
        assert await is_event_favorite(session, user, event.id) is False


@pytest.mark.anyio
async def test_rating_summaries_average_excludes_unverified_users(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        category = await make_category(session)
        creator = await make_user(session, telegram_id=1)
        event = await make_event(
            session, creator, category, status=EventStatus.APPROVED.value
        )

        verified = await make_user(session, telegram_id=2, is_verified=True)
        unverified = await make_user(session, telegram_id=3, is_verified=False)
        session.add(Rating(user_id=verified.id, event_id=event.id, score=4))
        session.add(Rating(user_id=unverified.id, event_id=event.id, score=1))
        await session.flush()

        summaries = await rating_summaries(session, [event.id])
        average, count = summaries[event.id]
        assert count == 1
        assert average == 4.0


@pytest.mark.anyio
async def test_compute_summary_counts_events_by_status(
    db_session, make_user, make_category, make_event
):
    async with db_session() as session:
        creator = await make_user(session)
        category = await make_category(session)
        await make_event(
            session, creator, category, status=EventStatus.APPROVED.value, title="A"
        )
        await make_event(
            session, creator, category, status=EventStatus.APPROVED.value, title="B"
        )
        await make_event(
            session, creator, category, status=EventStatus.PENDING.value, title="C"
        )
        await make_event(
            session, creator, category, status=EventStatus.REJECTED.value, title="D"
        )

        summary = await compute_summary(session, AnalyticsFilters())

        assert summary["total_events"] == 4
        assert summary["approved"] == 2
        assert summary["rejected"] == 1
        assert summary["pending_review"] == 1
