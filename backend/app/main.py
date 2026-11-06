from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.router import router as api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.database.mongodb.client import close_mongo, init_mongo
from app.database.postgres.engine import dispose_engine, init_engine
from app.database.postgres.session import init_session_factory
from app.database.qdrant.client import close_qdrant, init_qdrant
from app.rag.runtime import init_embedding_providers


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    setup_logging(runtime_settings.log_level, runtime_settings.app_env)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = init_engine(runtime_settings)
        init_session_factory(engine)
        init_mongo(runtime_settings)
        init_qdrant(runtime_settings)
        init_embedding_providers(runtime_settings)
        try:
            yield
        finally:
            await close_mongo()
            await close_qdrant()
            await dispose_engine()

    is_development = runtime_settings.app_env == "development"
    app = FastAPI(
        title="Agentic Procurement API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if is_development else None,
        redoc_url="/redoc" if is_development else None,
        openapi_url="/openapi.json" if is_development else None,
    )
    app.state.settings = runtime_settings

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)

    return app


app = create_app()
