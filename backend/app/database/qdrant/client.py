from qdrant_client import AsyncQdrantClient

from app.core.config import Settings

_client: AsyncQdrantClient | None = None


def init_qdrant(settings: Settings) -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return _client


def get_qdrant() -> AsyncQdrantClient:
    if _client is None:
        raise RuntimeError("qdrant client has not been initialized")
    return _client


async def close_qdrant() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
