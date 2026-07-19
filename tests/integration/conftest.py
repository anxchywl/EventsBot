from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date, time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests that require external services"
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        item.add_marker("integration")
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(
        reason="set TEST_DATABASE_URL (and run migrations) to enable integration tests"
    )
    for item in items:
        item.add_marker(skip)


@asynccontextmanager
async def _rollback_session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        # integrity errors can leave the transaction already rolled back
        if trans.is_active:
            await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture
def db_session():
    return _rollback_session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def make_user():
    async def _make(session, *, telegram_id=1001, role="user", is_verified=True, **kw):
        from app.models.user import User

        user = User(
            telegram_id=telegram_id,
            role=role,
            is_verified=is_verified,
            first_name=kw.pop("first_name", "Test"),
            **kw,
        )
        session.add(user)
        await session.flush()
        return user

    return _make


@pytest.fixture
def make_category():
    async def _make(session, *, name="Tech", slug="tech", is_active=True):
        from app.models.event import EventCategory

        category = EventCategory(name=name, slug=slug, is_active=is_active)
        session.add(category)
        await session.flush()
        return category

    return _make


@pytest.fixture
def make_event():
    async def _make(
        session,
        creator,
        category,
        *,
        status=None,
        title="Robotics Night",
        event_date=date(2099, 5, 1),
        event_time=time(18, 0),
        event_end_time=time(20, 0),
        location="Block C",
        parent_event_id=None,
        client_request_id=None,
        client_request_fingerprint=None,
    ):
        from app.services.events import create_pending_event

        event = await create_pending_event(
            session,
            creator=creator,
            event_data={
                "title": title,
                "client_request_id": client_request_id,
                "client_request_fingerprint": client_request_fingerprint,
                "description": "Come build robots",
                "event_date": event_date,
                "event_time": event_time,
                "event_end_time": event_end_time,
                "location": location,
                "category_id": category.id,
                "organizer": "Robotics Club",
            },
        )
        if parent_event_id is not None:
            event.parent_event_id = parent_event_id
        if status is not None:
            event.status = status
        await session.flush()
        return event

    return _make
