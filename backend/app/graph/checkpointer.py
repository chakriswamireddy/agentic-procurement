"""Postgres checkpointer lifecycle.

The checkpointer uses its own connection string and connection pool. It is never
request-scoped and never shares the application's asyncpg engine. Checkpoints contain
graph execution state and metadata; business approval rows live in PostgreSQL tables.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def checkpointer_context(settings: Settings) -> AsyncIterator[object]:
    if not settings.graph_checkpointer_enabled:
        logger.info("graph checkpointer disabled; using in-memory checkpoints")
        yield InMemorySaver()
        return

    async with AsyncPostgresSaver.from_conn_string(
        settings.checkpointer_database_url
    ) as saver:
        await saver.setup()
        logger.info("postgres workflow checkpointer ready")
        yield saver
