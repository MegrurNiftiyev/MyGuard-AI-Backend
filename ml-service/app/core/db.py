"""
MongoDB async client using Motor.

Provides a singleton client and a convenience accessor for the database handle.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """Initialise the Motor client. Call once at app startup."""
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    _db = _client[settings.DB_NAME]


async def close_db() -> None:
    """Close the Motor client. Call once at app shutdown."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the database handle. Raises if connect_db() hasn't been called."""
    if _db is None:
        raise RuntimeError(
            "Database not initialised — call connect_db() during app startup"
        )
    return _db
