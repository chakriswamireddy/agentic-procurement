"""Redis client lifecycle and connection management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import redis.asyncio as redis

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def init_redis(settings: Settings) -> redis.Redis:
    """Initialize a singleton async Redis client during application startup."""
    global _client
    if _client is None:
        _client = redis.from_url(
            settings.redis_url,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            health_check_interval=30,
            decode_responses=True,
        )
        logger.info("initialized async redis client", extra={"url": settings.redis_url})
    return _client


def get_redis() -> redis.Redis:
    """Return the initialized Redis client singleton."""
    if _client is None:
        raise RuntimeError("redis client has not been initialized")
    return _client


async def close_redis() -> None:
    """Close the Redis client connection pool gracefully during shutdown."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
            logger.info("closed async redis client connection")
        except Exception as exc:
            logger.warning("error while closing redis client: %s", exc)
        finally:
            _client = None
