import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("MINIAPP_SESSION_TTL_SECONDS", "86400")

import app.web.main as web_main  # noqa: E402
import app.web.routers.flutter_analytics as fa  # noqa: E402
from app.services.analytics_dashboard import AnalyticsFilters  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class HealthProbeTest(unittest.TestCase):
    def test_liveness_is_dependency_free(self):
        # liveness must not flap on Postgres/Redis hiccups
        self.assertEqual(_run(web_main.health()), {"status": "ok"})

    def _ready(self, *, db_ok=True, redis_ok=True):
        session = AsyncMock()
        if not db_ok:
            session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        ping = AsyncMock(side_effect=None if redis_ok else RuntimeError("redis down"))
        redis = SimpleNamespace(ping=ping)
        with patch.object(web_main, "get_redis", return_value=redis):
            response = _run(web_main.health_ready(session=session))
        return response.status_code, json.loads(response.body)

    def test_ready_when_all_dependencies_up(self):
        status_code, body = self._ready()
        self.assertEqual(status_code, 200)
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["checks"], {"database": "ok", "redis": "ok"})

    def test_degraded_returns_503_when_database_down(self):
        # 503 (not 500) lets a load balancer drain the instance without alerting
        status_code, body = self._ready(db_ok=False)
        self.assertEqual(status_code, 503)
        self.assertEqual(body["checks"]["database"], "error")
        self.assertEqual(body["checks"]["redis"], "ok")

    def test_degraded_returns_503_when_redis_down(self):
        status_code, body = self._ready(redis_ok=False)
        self.assertEqual(status_code, 503)
        self.assertEqual(body["checks"]["redis"], "error")


class AnalyticsCacheKeyTest(unittest.TestCase):
    """Regression: a free-text filter value (e.g. an organizer name) that
    contains the old '|' separator must never be reinterpreted as a field
    boundary and collide with a genuinely different filter set."""

    def test_same_filters_produce_the_same_key(self):
        f = AnalyticsFilters(organizer="Robotics", status="approved")
        self.assertEqual(fa._cache_key("summary", f), fa._cache_key("summary", f))

    def test_pipe_in_organizer_does_not_collide_with_other_filters(self):
        pipe = AnalyticsFilters(organizer="a|approved")
        split = AnalyticsFilters(organizer="a", status="approved")
        self.assertNotEqual(
            fa._cache_key("summary", pipe), fa._cache_key("summary", split)
        )

    def test_metric_name_and_extra_args_separate_keys(self):
        f = AnalyticsFilters()
        self.assertNotEqual(fa._cache_key("summary", f), fa._cache_key("ratings", f))
        self.assertNotEqual(
            fa._cache_key("top", f, "views"), fa._cache_key("top", f, "shares")
        )


if __name__ == "__main__":
    unittest.main()
