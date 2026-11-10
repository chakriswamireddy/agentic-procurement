import asyncio
import time
from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, Request, Response
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from app.core.config import Settings
from app.database.mongodb.client import get_database
from app.database.postgres.engine import get_engine
from app.database.redis.client import get_redis, init_redis

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 2.5


async def _timed_check(operation: Awaitable[Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(operation, timeout=CHECK_TIMEOUT_SECONDS)
    except Exception:
        return {
            "status": "down",
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }
    return {
        "status": "ok",
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


async def _check_postgres() -> None:
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _check_mongodb() -> None:
    await get_database().command("ping")


async def _check_redis(settings: Settings) -> None:
    try:
        client = get_redis()
    except RuntimeError:
        client = init_redis(settings)
    await client.ping()


async def _check_qdrant(settings: Settings) -> None:
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        await client.get_collections()
    finally:
        await client.close()


@router.get("/health/live", operation_id="health_live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", operation_id="health_ready")
async def health_ready(request: Request, response: Response) -> dict[str, Any]:
    settings: Settings = request.app.state.settings

    names = ("postgres", "mongodb", "redis", "qdrant")
    required = {"postgres": True, "mongodb": False, "redis": False, "qdrant": False}

    results = await asyncio.gather(
        _timed_check(_check_postgres()),
        _timed_check(_check_mongodb()),
        _timed_check(_check_redis(settings)),
        _timed_check(_check_qdrant(settings)),
    )

    checks = {
        name: {**result, "required": required[name]}
        for name, result in zip(names, results, strict=True)
    }

    ready = all(check["status"] == "ok" for check in checks.values() if check["required"])
    if not ready:
        response.status_code = 503

    return {"status": "ready" if ready else "not_ready", "checks": checks}
