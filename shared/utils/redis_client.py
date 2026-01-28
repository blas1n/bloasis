"""
Redis client utility for BLOASIS services.

Provides async Redis operations for caching with JSON serialization support.
"""

import json
import logging
import os
from typing import Any, Optional

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Async Redis client for caching operations.

    Uses environment variables for configuration:
    - REDIS_HOST: Redis server hostname (default: 'redis')
    - REDIS_PORT: Redis server port (default: 6379)

    Example:
        client = RedisClient()
        await client.connect()
        await client.setex("key", 3600, {"data": "value"})
        data = await client.get("key")
        await client.close()
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        """
        Initialize Redis client configuration.

        Args:
            host: Redis server hostname. Defaults to REDIS_HOST env var or 'redis'.
            port: Redis server port. Defaults to REDIS_PORT env var or 6379.
        """
        self.host: str = host if host is not None else (os.getenv("REDIS_HOST") or "redis")
        self.port: int = port if port is not None else int(os.getenv("REDIS_PORT") or "6379")
        self.client: Optional[redis.Redis] = None  # type: ignore[type-arg]

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
                decode_responses=True,
            )
            await self.client.ping()  # type: ignore[misc]
            logger.info(
                "Connected to Redis",
                extra={"host": self.host, "port": self.port},
            )
        except RedisError as e:
            logger.error(
                "Redis connection failed",
                extra={"host": self.host, "port": self.port, "error": str(e)},
            )
            raise ConnectionError(f"Failed to connect to Redis at {self.host}:{self.port}: {e}") from e

    async def close(self) -> None:
        """
        Close the Redis connection.
        """
        if self.client is not None:
            await self.client.aclose()
            self.client = None
            logger.info(
                "Disconnected from Redis",
                extra={"host": self.host, "port": self.port},
            )

    async def get(self, key: str) -> Optional[Any]:
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
            serialized = json.dumps(value)
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
