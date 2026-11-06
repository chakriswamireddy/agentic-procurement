from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("session factory has not been initialized")
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
