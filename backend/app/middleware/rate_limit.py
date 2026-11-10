"""Rate limiting middleware and dependency providers."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status

from app.database.redis.client import get_redis
from app.database.redis.rate_limit import RedisRateLimiter

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """Safely extract client IP from connection."""
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def get_rate_limiter(request: Request) -> RedisRateLimiter:
    """Dependency provider for RedisRateLimiter using shared Redis client."""
    try:
        redis_client = get_redis()
        return RedisRateLimiter(redis_client, fail_open=True)
    except Exception:
        return RedisRateLimiter(None, fail_open=True)


async def _extract_identity(request: Request) -> str:
    """Best-effort identity for rate limiting from JSON or form login bodies."""
    email = ""
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            body = await request.json()
            email = str(body.get("email") or body.get("username") or "")
        except Exception:
            email = ""
    elif "application/x-www-form-urlencoded" in content_type or "multipart" in content_type:
        try:
            form = await request.form()
            email = str(form.get("username") or form.get("email") or "")
        except Exception:
            email = ""
    return f"{get_client_ip(request)}:{email.strip().lower()}"


async def check_auth_rate_limit(
    request: Request,
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    response: Response,
) -> None:
    """Enforce a strict per-identity rate limit on authentication endpoints."""
    settings = getattr(request.app.state, "settings", None)
    if settings is not None and not getattr(settings, "auth_rate_limit_enabled", True):
        return
    limit = getattr(settings, "auth_rate_limit_requests", 5) if settings else 5
    window = getattr(settings, "auth_rate_limit_window_seconds", 60) if settings else 60
    identity = await _extract_identity(request)

    is_limited, retry_after, _ = await limiter.check_rate_limit(
        scope="auth",
        identity=identity,
        limit=limit,
        window_seconds=window,
    )

    if is_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
