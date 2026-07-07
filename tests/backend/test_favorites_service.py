import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.services.favorites import (  # noqa: E402
    add_favorite,
    get_favorite_event_ids,
    is_event_favorite,
    remove_favorite,
)


def _run(coro):
    return asyncio.run(coro)


def _user():
    return SimpleNamespace(id=7)


def _event():
    return SimpleNamespace(id=42)


class IsFavoriteTest(unittest.TestCase):
    def test_anonymous_user_is_never_favorite(self):
        session = AsyncMock()
        self.assertFalse(_run(is_event_favorite(session, None, 42)))
        session.scalar.assert_not_called()

    def test_present_row_means_favorite(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=1)
        self.assertTrue(_run(is_event_favorite(session, _user(), 42)))

    def test_absent_row_means_not_favorite(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        self.assertFalse(_run(is_event_favorite(session, _user(), 42)))


class FavoriteIdsTest(unittest.TestCase):
    def test_no_user_or_ids_short_circuits(self):
        session = AsyncMock()
        self.assertEqual(_run(get_favorite_event_ids(session, None, [1, 2])), set())
        self.assertEqual(_run(get_favorite_event_ids(session, _user(), [])), set())
        session.execute.assert_not_called()


class AddFavoriteTest(unittest.TestCase):
    def test_duplicate_is_not_added_again(self):
        # idempotent: saving an already-saved event is a no-op returning False
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=1)  # already a favorite
        session.add = lambda *_a, **_k: None
        self.assertFalse(_run(add_favorite(session, _user(), _event())))

    def test_new_favorite_is_added_and_flushed(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        added = []
        session.add = lambda obj: added.append(obj)
        session.flush = AsyncMock()
        self.assertTrue(_run(add_favorite(session, _user(), _event())))
        self.assertEqual(len(added), 1)
        session.flush.assert_awaited_once()

    def test_race_integrity_error_is_swallowed(self):
        # a concurrent insert that trips the unique constraint rolls back cleanly
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.add = lambda *_a, **_k: None
        session.flush = AsyncMock(side_effect=IntegrityError("x", "y", Exception()))
        session.rollback = AsyncMock()
        self.assertFalse(_run(add_favorite(session, _user(), _event())))
        session.rollback.assert_awaited_once()


class RemoveFavoriteTest(unittest.TestCase):
    def _session(self, deleted_id):
        session = AsyncMock()
        result = SimpleNamespace(scalar_one_or_none=lambda: deleted_id)
        session.execute = AsyncMock(return_value=result)
        return session

    def test_remove_existing_returns_true(self):
        self.assertTrue(_run(remove_favorite(self._session(1), _user(), _event())))

    def test_remove_absent_returns_false(self):
        self.assertFalse(_run(remove_favorite(self._session(None), _user(), _event())))


if __name__ == "__main__":
    unittest.main()
