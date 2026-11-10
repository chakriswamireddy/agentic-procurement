"""Tests for Redis supplier search caching layer (Phase 6, Step 6.2)."""

import json
from unittest.mock import AsyncMock

import pytest
from app.database.redis.cache import (
    SupplierCache,
)
from app.services.supplier_service import SupplierService


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.is_down = False

    async def get(self, key: str) -> str | None:
        if self.is_down:
            raise ConnectionError("Redis is unreachable")
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if self.is_down:
            raise ConnectionError("Redis is unreachable")
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex

    async def incr(self, key: str) -> int:
        if self.is_down:
            raise ConnectionError("Redis is unreachable")
        val = int(self.data.get(key, "1")) + 1
        self.data[key] = str(val)
        return val


class CountingSupplierRepo:
    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.call_count = 0

    async def list_suppliers(self, **kwargs) -> tuple[list[dict], int]:
        self.call_count += 1
        return self.items, len(self.items)


@pytest.fixture
def fake_supplier_data() -> list[dict]:
    return [
        {
            "id": "SUP0001",
            "name": "Apex Office Supplies",
            "category": "office_supplies",
            "location": "North America",
            "status": "active",
        }
    ]


@pytest.mark.asyncio
async def test_supplier_cache_miss_then_hit(fake_supplier_data):
    redis_client = FakeRedis()
    cache = SupplierCache(redis_client, base_ttl=60)
    repo = CountingSupplierRepo(fake_supplier_data)
    service = SupplierService(suppliers=repo, profiles=AsyncMock(), cache=cache)

    # First call: cache miss, repo called once
    res1 = await service.list_suppliers(category="office_supplies")
    assert len(res1.items) == 1
    assert repo.call_count == 1
    assert cache.miss_count == 1
    assert cache.hit_count == 0

    # Second call: cache hit, repo call_count remains 1
    res2 = await service.list_suppliers(category="office_supplies")
    assert len(res2.items) == 1
    assert repo.call_count == 1
    assert cache.hit_count == 1


@pytest.mark.asyncio
async def test_supplier_cache_ttl_is_positive_and_jittered(fake_supplier_data):
    redis_client = FakeRedis()
    cache = SupplierCache(redis_client, base_ttl=60)
    repo = CountingSupplierRepo(fake_supplier_data)
    service = SupplierService(suppliers=repo, profiles=AsyncMock(), cache=cache)

    await service.list_suppliers(category="office_supplies")

    # Verify TTL was recorded and is within jitter range 54..66
    assert len(redis_client.ttls) == 1
    ttl = next(iter(redis_client.ttls.values()))
    assert 50 <= ttl <= 70


@pytest.mark.asyncio
async def test_supplier_cache_invalidation_by_version_bump(fake_supplier_data):
    redis_client = FakeRedis()
    cache = SupplierCache(redis_client, base_ttl=60)
    repo = CountingSupplierRepo(fake_supplier_data)
    service = SupplierService(suppliers=repo, profiles=AsyncMock(), cache=cache)

    # Initial population
    await service.list_suppliers(category="office_supplies")
    assert repo.call_count == 1

    # Bump cache version
    new_version = await cache.bump_cache_version()
    assert new_version == 2

    # Query again: should cause a miss because version changed from 1 to 2
    res = await service.list_suppliers(category="office_supplies")
    assert len(res.items) == 1
    assert repo.call_count == 2


@pytest.mark.asyncio
async def test_supplier_cache_fail_open_when_redis_down(fake_supplier_data):
    redis_client = FakeRedis()
    cache = SupplierCache(redis_client, base_ttl=60)
    repo = CountingSupplierRepo(fake_supplier_data)
    service = SupplierService(suppliers=repo, profiles=AsyncMock(), cache=cache)

    # Simulate Redis outage
    redis_client.is_down = True

    # Request succeeds directly from repo without crashing
    res = await service.list_suppliers(category="office_supplies")
    assert len(res.items) == 1
    assert repo.call_count == 1


@pytest.mark.asyncio
async def test_supplier_cache_ignores_incompatible_schema_version(fake_supplier_data):
    redis_client = FakeRedis()
    cache = SupplierCache(redis_client, base_ttl=60)
    repo = CountingSupplierRepo(fake_supplier_data)
    service = SupplierService(suppliers=repo, profiles=AsyncMock(), cache=cache)

    # Pre-populate with incompatible schema version 99
    version = await cache.get_cache_version()
    key = cache.compute_cache_key(
        version=version,
        category="office_supplies",
        location=None,
        status=None,
        q=None,
        limit=20,
        offset=0,
    )
    bad_payload = {
        "schema_version": 99,
        "data": {
            "items": fake_supplier_data,
            "total": 1,
            "limit": 20,
            "offset": 0,
        },
    }
    redis_client.data[key] = json.dumps(bad_payload)

    # Call service: should detect outdated schema, ignore it, and call repo
    res = await service.list_suppliers(category="office_supplies")
    assert len(res.items) == 1
    assert repo.call_count == 1
