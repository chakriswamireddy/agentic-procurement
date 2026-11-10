"""Tests for Redis distributed rate limiter (Phase 6, Step 6.3)."""

from unittest.mock import AsyncMock

import pytest
from app.database.redis.rate_limit import RedisRateLimiter
from app.main import create_app
from httpx import ASGITransport, AsyncClient


class FakeRateLimitRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.is_down = False

    async def eval(self, script: str, numkeys: int, key: str, window_seconds: int):
        if self.is_down:
            raise ConnectionError("Redis is unreachable")
        current = self.counts.get(key, 0) + 1
        self.counts[key] = current
        ttl = max(1, window_seconds - 5)
        return [current, ttl]


@pytest.mark.asyncio
async def test_rate_limiter_5_allowed_6th_blocked():
    redis_mock = FakeRateLimitRedis()
    limiter = RedisRateLimiter(redis_mock, fail_open=True)

    identity = "192.168.1.1:user@example.com"

    for i in range(5):
        is_limited, retry_after, remaining = await limiter.check_rate_limit(
            scope="auth", identity=identity, limit=5, window_seconds=60
        )
        assert is_limited is False
        assert remaining == 5 - (i + 1)
        assert retry_after == 0

    # 6th attempt must be limited
    is_limited, retry_after, remaining = await limiter.check_rate_limit(
        scope="auth", identity=identity, limit=5, window_seconds=60
    )
    assert is_limited is True
    assert retry_after > 0
    assert remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_identity_isolation():
    redis_mock = FakeRateLimitRedis()
    limiter = RedisRateLimiter(redis_mock, fail_open=True)

    # Identity 1 exhausts 5 attempts
    for _ in range(5):
        await limiter.check_rate_limit(
            scope="auth", identity="10.0.0.1:alice@example.com", limit=5, window_seconds=60
        )

    # Identity 1 is now limited
    is_limited_alice, _, _ = await limiter.check_rate_limit(
        scope="auth", identity="10.0.0.1:alice@example.com", limit=5, window_seconds=60
    )
    assert is_limited_alice is True

    # Identity 2 (different user or different IP) is NOT limited
    is_limited_bob, _, remaining_bob = await limiter.check_rate_limit(
        scope="auth", identity="10.0.0.2:bob@example.com", limit=5, window_seconds=60
    )
    assert is_limited_bob is False
    assert remaining_bob == 4


@pytest.mark.asyncio
async def test_rate_limiter_fail_open_on_redis_error():
    redis_mock = FakeRateLimitRedis()
    redis_mock.is_down = True
    limiter = RedisRateLimiter(redis_mock, fail_open=True)

    # Outage should fail open and not block legitimate access
    is_limited, retry_after, remaining = await limiter.check_rate_limit(
        scope="auth", identity="10.0.0.1:alice@example.com", limit=5, window_seconds=60
    )
    assert is_limited is False
    assert retry_after == 0


@pytest.mark.asyncio
async def test_rate_limiter_fail_closed_configuration():
    redis_mock = FakeRateLimitRedis()
    redis_mock.is_down = True
    limiter = RedisRateLimiter(redis_mock, fail_open=False)

    # Configured to fail closed
    is_limited, retry_after, remaining = await limiter.check_rate_limit(
        scope="auth", identity="10.0.0.1:alice@example.com", limit=5, window_seconds=60
    )
    assert is_limited is True
    assert retry_after == 60


@pytest.mark.asyncio
async def test_auth_login_endpoint_returns_429():
    from app.core.config import get_settings

    settings = get_settings().model_copy(update={"auth_rate_limit_enabled": True})
    app = create_app(settings)

    fake_redis = FakeRateLimitRedis()
    mock_limiter = RedisRateLimiter(fake_redis, fail_open=True)

    from app.api.deps import get_auth_service
    from app.middleware.rate_limit import get_rate_limiter
    app.dependency_overrides[get_rate_limiter] = lambda: mock_limiter

    mock_auth = AsyncMock()
    mock_auth.authenticate.side_effect = Exception("invalid credentials")
    app.dependency_overrides[get_auth_service] = lambda: mock_auth

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Exhaust 5 attempts
        for _ in range(5):
            await client.post(
                "/api/v1/auth/login",
                json={"email": "limit_test@example.com", "password": "wrongpassword"},
            )

        # 6th attempt must return 429 Too Many Requests
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "limit_test@example.com", "password": "wrongpassword"},
        )
        assert res.status_code == 429
        assert "Retry-After" in res.headers
        data = res.json()
        assert data["error"]["code"] == "rate_limited"
        assert "Too many authentication attempts" in data["error"]["message"]
