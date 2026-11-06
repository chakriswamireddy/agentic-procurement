from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings

_client: AsyncMongoClient | None = None
_database_name: str | None = None


def init_mongo(settings: Settings) -> AsyncMongoClient:
    global _client, _database_name
    if _client is None:
        _client = AsyncMongoClient(
            settings.mongodb_url,
            serverSelectionTimeoutMS=3000,
        )
        _database_name = settings.mongodb_db
    return _client


def get_client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("mongo client has not been initialized")
    return _client


def get_database() -> AsyncDatabase:
    if _client is None or _database_name is None:
        raise RuntimeError("mongo client has not been initialized")
    return _client[_database_name]


async def close_mongo() -> None:
    global _client, _database_name
    if _client is not None:
        await _client.close()
        _client = None
        _database_name = None
