"""Distributed Redis rate limiter using atomic Lua scripts and anonymized identity hashing."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

from app.core.logging import get_correlation_id

if TYPE_CHECKING:
    import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Atomic fixed-window rate limit script in Lua
# Keys: [rate_limit_key]
# Args: [window_seconds]
# Returns: [current_count, ttl_remaining]
LUA_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    ttl = ARGV[1]
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {current, ttl}
"""


class RedisRateLimiter:
    """Fixed-window atomic rate limiter backed by Redis with fail-open fault tolerance."""

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        *,
        fail_open: bool = True,
    ) -> None:
        self.redis = redis_client
        self.fail_open = fail_open
        self._script = None

    @staticmethod
    def hash_identity(identifier: str) -> str:
        """Hash raw identity (IP + email/subject) to prevent storing PII in Redis."""
        return hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest()[:16]

    async def check_rate_limit(
        self,
        scope: str,
        identity: str,
        *,
        limit: int = 5,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int]:
        """Check and increment rate limit for a given identity.

        Returns:
            Tuple of (is_limited, retry_after_seconds, remaining_requests)
        """
        if self.redis is None:
            return False, 0, limit

        identity_hash = self.hash_identity(identity)
        window_id = int(time.time() // window_seconds)
        cache_key = f"ratelimit:{scope}:{identity_hash}:{window_id}"

        try:
            res = await self.redis.eval(LUA_RATE_LIMIT_SCRIPT, 1, cache_key, window_seconds)
            current_count, ttl = int(res[0]), max(1, int(res[1]))

            if current_count > limit:
                logger.warning(
                    "rate limit exceeded",
                    extra={
                        "correlation_id": get_correlation_id(),
                        "scope": scope,
                        "identity_hash": identity_hash,
                        "count": current_count,
                        "limit": limit,
                        "retry_after": ttl,
                    },
                )
                return True, ttl, 0

            remaining = max(0, limit - current_count)
            return False, 0, remaining

        except (RedisError, ConnectionError, Exception) as exc:
            if self.fail_open:
                logger.warning(
                    "redis rate limiter unavailable; failing open",
                    extra={
                        "correlation_id": get_correlation_id(),
                        "scope": scope,
                        "error": str(exc),
                    },
                )
                return False, 0, limit
            else:
                logger.error(
                    "redis rate limiter unavailable; failing closed",
                    extra={
                        "correlation_id": get_correlation_id(),
                        "scope": scope,
                        "error": str(exc),
                    },
                )
                return True, window_seconds, 0
