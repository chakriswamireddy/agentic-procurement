"""Redis cache: supplier search cache-aside, TTL jitter, versioned invalidation."""

from __future__ import annotations

import hashlib
import json
import logging
import random
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

from app.core.logging import get_correlation_id
from app.schemas.supplier import SupplierList

if TYPE_CHECKING:
    import redis.asyncio as redis

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 1
DEFAULT_CACHE_TTL_SECONDS = 60
CACHE_VERSION_KEY = "suppliers:cache_version"


class SupplierCache:
    """Async Redis cache for supplier directory queries using cache-aside pattern."""

    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        base_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
        enabled: bool = True,
    ) -> None:
        self.redis = redis_client
        self.base_ttl = base_ttl
        self.enabled = enabled
        self.hit_count = 0
        self.miss_count = 0

    async def get_cache_version(self) -> int:
        """Fetch the current global cache version, defaulting to 1 on miss or failure."""
        if not self.enabled:
            return 1
        try:
            val = await self.redis.get(CACHE_VERSION_KEY)
            if val is not None:
                return int(val)
            return 1
        except (RedisError, ConnectionError, ValueError) as exc:
            logger.warning(
                "failed to get supplier cache version; falling back to default",
                extra={"correlation_id": get_correlation_id(), "error": str(exc)},
            )
            return 1

    async def bump_cache_version(self) -> int:
        """Atomically bump the supplier cache version, invalidating all current entries."""
        if not self.enabled:
            return 1
        try:
            new_version = await self.redis.incr(CACHE_VERSION_KEY)
            logger.info(
                "bumped supplier cache version",
                extra={"correlation_id": get_correlation_id(), "version": new_version},
            )
            return int(new_version)
        except (RedisError, ConnectionError) as exc:
            logger.warning(
                "failed to bump supplier cache version",
                extra={"correlation_id": get_correlation_id(), "error": str(exc)},
            )
            return 1

    def compute_cache_key(
        self,
        *,
        version: int,
        category: str | None = None,
        location: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """Generate a deterministic versioned cache key from normalized query filters."""
        filter_payload = {
            "category": category or "",
            "location": location or "",
            "status": status or "",
            "q": q or "",
            "limit": limit,
            "offset": offset,
        }
        serialized = json.dumps(filter_payload, sort_keys=True)
        query_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"suppliers:v{version}:{query_hash}"

    async def get_supplier_list(self, cache_key: str) -> SupplierList | None:
        """Retrieve and validate cached SupplierList payload."""
        if not self.enabled:
            return None
        try:
            raw = await self.redis.get(cache_key)
            if raw is None:
                self.miss_count += 1
                logger.debug(
                    "supplier cache miss",
                    extra={"correlation_id": get_correlation_id(), "cache_key": cache_key},
                )
                return None

            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return None

            # Verify schema compatibility
            if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
                logger.warning(
                    "cached supplier payload schema mismatch; ignoring entry",
                    extra={
                        "correlation_id": get_correlation_id(),
                        "expected_version": CACHE_SCHEMA_VERSION,
                        "cached_version": payload.get("schema_version"),
                    },
                )
                return None

            data = payload.get("data")
            if not data or not isinstance(data, dict):
                return None

            self.hit_count += 1
            logger.debug(
                "supplier cache hit",
                extra={"correlation_id": get_correlation_id(), "cache_key": cache_key},
            )
            return SupplierList.model_validate(data)

        except (RedisError, ConnectionError, json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "supplier cache get error; bypassing cache",
                extra={"correlation_id": get_correlation_id(), "error": str(exc)},
            )
            return None

    async def set_supplier_list(
        self,
        cache_key: str,
        supplier_list: SupplierList,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store SupplierList in Redis with TTL jitter."""
        if not self.enabled:
            return
        try:
            base = ttl_seconds if ttl_seconds is not None else self.base_ttl
            # ±10% jitter to prevent synchronized expiry
            jitter = random.uniform(0.9, 1.1)
            effective_ttl = max(1, int(base * jitter))

            payload = {
                "schema_version": CACHE_SCHEMA_VERSION,
                "data": supplier_list.model_dump(mode="json"),
            }
            await self.redis.set(cache_key, json.dumps(payload), ex=effective_ttl)
            logger.debug(
                "populated supplier cache",
                extra={
                    "correlation_id": get_correlation_id(),
                    "cache_key": cache_key,
                    "ttl": effective_ttl,
                },
            )
        except (RedisError, ConnectionError, Exception) as exc:
            logger.warning(
                "supplier cache set error; skipping cache write",
                extra={"correlation_id": get_correlation_id(), "error": str(exc)},
            )
