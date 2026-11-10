"""Redis caching layer with graceful degradation and JSON serialization."""

import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisCache:
    """Async Redis cache client with fault-tolerant operations."""

    def __init__(
        self,
        redis_url: str,
        *,
        enabled: bool = True,
        default_ttl_seconds: int = 3600,
    ) -> None:
        self.redis_url = redis_url
        self.enabled = enabled
        self.default_ttl = default_ttl_seconds
        self._client: redis.Redis | None = None

    def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
        return self._client

    async def get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        try:
            client = self._get_client()
            raw = await client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except (RedisError, ConnectionError, json.JSONDecodeError) as exc:
            logger.warning(
                "redis cache get error: bypassing cache",
                extra={"key": key, "error": str(exc)},
            )
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        if not self.enabled:
            return
        try:
            client = self._get_client()
            raw = json.dumps(value, default=str)
            await client.set(key, raw, ex=ttl_seconds or self.default_ttl)
        except (RedisError, ConnectionError) as exc:
            logger.warning(
                "redis cache set error: bypassing cache",
                extra={"key": key, "error": str(exc)},
            )

    async def delete(self, key: str) -> None:
        if not self.enabled:
            return
        try:
            client = self._get_client()
            await client.delete(key)
        except (RedisError, ConnectionError) as exc:
            logger.warning(
                "redis cache delete error",
                extra={"key": key, "error": str(exc)},
            )

    async def delete_by_prefix(self, prefix: str) -> int:
        if not self.enabled:
            return 0
        try:
            client = self._get_client()
            deleted = 0
            cursor = 0
            pattern = f"{prefix}*"
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    deleted += await client.delete(*keys)
                if cursor == 0:
                    break
            return deleted
        except (RedisError, ConnectionError) as exc:
            logger.warning(
                "redis cache delete_by_prefix error",
                extra={"prefix": prefix, "error": str(exc)},
            )
            return 0

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
