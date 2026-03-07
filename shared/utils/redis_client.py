"""
Redis client utility for BLOASIS services.

Provides async Redis operations for caching with JSON serialization support.
"""

import json
import logging
import os
from decimal import Decimal
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class RedisClient:
    """
    Async Redis client for caching operations.

    Uses environment variables for configuration:
    - REDIS_HOST: Redis server hostname (default: 'redis')
    - REDIS_PORT: Redis server port (default: 6379)
    - REDIS_PASSWORD: Redis server password (default: None)

    Example:
        client = RedisClient()
        await client.connect()
        await client.setex("key", 3600, {"data": "value"})
        data = await client.get("key")
        await client.close()
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
    ) -> None:
        self.host: str = host if host is not None else (os.getenv("REDIS_HOST") or "redis")
        self.port: int = port if port is not None else int(os.getenv("REDIS_PORT") or "6379")
        self.password: str | None = password or os.getenv("REDIS_PASSWORD") or None
        self.client: redis.Redis | None = None  # type: ignore[type-arg]

    async def connect(self) -> None:
        """
        Establish connection to Redis server.

        Raises:
            ConnectionError: If connection to Redis fails.
        """
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                decode_responses=True,
            )
            await self.client.ping()
            logger.info(
                "Connected to Redis",
                extra={"host": self.host, "port": self.port},
            )
        except RedisError as e:
            logger.error(
                "Redis connection failed",
                extra={"host": self.host, "port": self.port, "error": str(e)},
            )
            raise ConnectionError(
                f"Failed to connect to Redis at {self.host}:{self.port}: {e}"
            ) from e

    async def close(self) -> None:
        """
        Close the Redis connection.
        """
        if self.client is not None:
            await self.client.close()
            self.client = None
            logger.info(
                "Disconnected from Redis",
                extra={"host": self.host, "port": self.port},
            )

    async def get(self, key: str) -> Any | None:
        """
        Get a value from Redis.

        Args:
            key: The cache key to retrieve.

        Returns:
            The cached value (deserialized from JSON if applicable), or None if key doesn't exist.

        Raises:
            ConnectionError: If not connected to Redis.
        """
        if self.client is None:
            raise ConnectionError("Redis client is not connected. Call connect() first.")

        value = await self.client.get(key)
        if value is None:
            return None

        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def setex(self, key: str, ttl: int, value: Any) -> None:
        """
        Set a value in Redis with a TTL (Time To Live).

        Args:
            key: The cache key.
            ttl: Time to live in seconds.
            value: The value to cache. Dicts and lists are serialized to JSON.

        Raises:
            ConnectionError: If not connected to Redis.
        """
        if self.client is None:
            raise ConnectionError("Redis client is not connected. Call connect() first.")

        if isinstance(value, (dict, list)):
            serialized = json.dumps(value, default=_json_default)
        else:
            serialized = str(value) if not isinstance(value, str) else value

        await self.client.setex(key, ttl, serialized)
        logger.debug(
            "Cache write",
            extra={"key": key, "ttl": ttl},
        )

    async def delete(self, key: str) -> None:
        """
        Delete a key from Redis.

        Args:
            key: The cache key to delete.

        Raises:
            ConnectionError: If not connected to Redis.
        """
        if self.client is None:
            raise ConnectionError("Redis client is not connected. Call connect() first.")

        await self.client.delete(key)
        logger.debug(
            "Cache invalidation",
            extra={"key": key},
        )
