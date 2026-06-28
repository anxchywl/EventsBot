import pytest
from fastapi import HTTPException

from app.web.limiter import check_rate_limit


class FakePipeline:
    def __init__(self, results):
        self.results = results
        self.commands = []

    def incr(self, key):
        self.commands.append(("incr", key))

    def expire(self, key, ttl, nx=False):
        self.commands.append(("expire", key, ttl, nx))

    def ttl(self, key):
        self.commands.append(("ttl", key))

    async def execute(self):
        return self.results


class FakeRedis:
    def __init__(self, results):
        self.pipeline_obj = FakePipeline(results)
        self.expire_calls = []

    def pipeline(self, transaction=True):
        return self.pipeline_obj

    async def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))


class TestUserInteractionsSecurity:
    @pytest.mark.anyio
    async def test_rate_limit_allows_request_under_limit(self, monkeypatch):
        redis = FakeRedis([1, True, 60])
        monkeypatch.setattr("app.web.limiter.get_redis", lambda: redis)

        await check_rate_limit("rate:user:1:fav", 30, 60)

        assert redis.pipeline_obj.commands == [
            ("incr", "rate:user:1:fav"),
            ("expire", "rate:user:1:fav", 60, True),
            ("ttl", "rate:user:1:fav"),
        ]

    @pytest.mark.anyio
    async def test_rate_limit_rejects_request_over_limit(self, monkeypatch):
        redis = FakeRedis([31, True, 60])
        monkeypatch.setattr("app.web.limiter.get_redis", lambda: redis)

        with pytest.raises(HTTPException) as exc:
            await check_rate_limit(
                "rate:user:1:fav", 30, 60, "Too many favorite attempts"
            )

        assert exc.value.status_code == 429
        assert exc.value.headers["Retry-After"] == "60"

    @pytest.mark.anyio
    async def test_rate_limit_repairs_missing_ttl(self, monkeypatch):
        redis = FakeRedis([1, True, -1])
        monkeypatch.setattr("app.web.limiter.get_redis", lambda: redis)

        await check_rate_limit("rate:user:1:fav", 30, 60)

        assert redis.expire_calls == [("rate:user:1:fav", 60)]
