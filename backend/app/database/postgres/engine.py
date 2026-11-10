from typing import Any

import asyncpg
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings

_engine: AsyncEngine | None = None


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_recycle=settings.database_pool_recycle,
        pool_pre_ping=settings.database_pool_pre_ping,
        connect_args={"command_timeout": int(settings.database_pool_timeout)},
    )


def init_engine(settings: Settings) -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("database engine has not been initialized")
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


def is_connection_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (asyncpg.PostgresConnectionError, ConnectionError, OSError)):
            return True
        if isinstance(current, SQLAlchemyError):
            orig: Any = getattr(current, "orig", None)
            if isinstance(orig, BaseException):
                current = orig
                continue
        cause: Any = current.__cause__ or current.__context__
        current = cause if isinstance(cause, BaseException) else None
    return False


def is_database_unavailable(exc: BaseException) -> bool:
    return is_connection_error(exc)
