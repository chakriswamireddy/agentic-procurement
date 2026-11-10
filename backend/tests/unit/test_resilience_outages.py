"""Dependency-outage behaviour for Phase 6 Step 6.12.

Each test pins one documented policy:
- Qdrant unavailable -> policy lookup is a 503 dependency error, never silent success.
- PostgreSQL (required) unavailable -> readiness is 503 while liveness stays 200.
- Corrupt cached supplier payload -> rejected and refetched, never served to clients.
"""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from app.api.v1 import health as health_module
from app.core.config import get_settings
from app.core.errors import DependencyUnavailableError
from app.database.redis.cache import SupplierCache
from app.main import create_app
from app.services.policy_service import PolicyService
from app.services.supplier_service import SupplierService
from qdrant_client.http.exceptions import ResponseHandlingException


class FailingRetriever:
    async def search(self, query, *, filters=None, limit=5, mode="hybrid"):
        raise ResponseHandlingException(ConnectionError("qdrant unreachable"))


async def test_qdrant_outage_maps_to_dependency_unavailable() -> None:
    service = PolicyService(FailingRetriever())

    with pytest.raises(DependencyUnavailableError):
        await service.search("approval threshold for capital purchases")


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def incr(self, key: str) -> int:
        current = int(self.data.get(key, "1")) + 1
        self.data[key] = str(current)
        return current


class CountingSupplierRepo:
    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.call_count = 0

    async def list_suppliers(self, **kwargs) -> tuple[list[dict], int]:
        self.call_count += 1
        return self.items, len(self.items)


async def test_corrupt_cached_payload_is_rejected_and_refetched() -> None:
    supplier = {
        "id": "SUP0001",
        "name": "Apex Office Supplies",
        "category": "office_supplies",
        "location": "North America",
        "status": "active",
    }
    redis_client = FakeRedis()
    cache = SupplierCache(redis_client, base_ttl=60)
    repo = CountingSupplierRepo([supplier])
    service = SupplierService(suppliers=repo, profiles=AsyncMock(), cache=cache)

    version = await cache.get_cache_version()
    key = cache.compute_cache_key(
        version=version,
        category="office_supplies",
        limit=20,
        offset=0,
    )
    redis_client.data[key] = "{not-valid-json"

    result = await service.list_suppliers(category="office_supplies")

    assert len(result.items) == 1
    assert repo.call_count == 1
    assert json.loads(redis_client.data[key])["schema_version"] == 1


async def test_readiness_is_503_when_required_postgres_is_down(monkeypatch) -> None:
    settings = get_settings()
    app = create_app(settings)

    async def postgres_down() -> None:
        raise ConnectionError("postgres unreachable")

    async def ok(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(health_module, "_check_postgres", postgres_down)
    monkeypatch.setattr(health_module, "_check_mongodb", ok)
    monkeypatch.setattr(health_module, "_check_redis", ok)
    monkeypatch.setattr(health_module, "_check_qdrant", ok)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 503
    body = ready.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"]["status"] == "down"
