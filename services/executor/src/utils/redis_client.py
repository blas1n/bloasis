"""Redis client for Executor Service."""

import logging
from typing import Any

import redis.asyncio as redis

from ..config import config

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client for order tracking and risk approval cache."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client: redis.Redis | None = None,
    ):
        """Initialize Redis client.

        Args:
            host: Redis host (default from config)
            port: Redis port (default from config)
            client: Optional pre-configured client (for testing)
        """
        self.host = host or config.redis_host
        self.port = port or config.redis_port
        self._client = client

    async def connect(self) -> None:
        """Connect to Redis."""
        if self._client is None:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                decode_responses=True,
            )
            # Test connection
            await self._client.ping()
            logger.info(f"Connected to Redis at {self.host}:{self.port}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Redis client closed")

    async def exists(self, key: str) -> bool:
        """Check if a key exists.

        Args:
            key: Redis key

        Returns:
            True if key exists, False otherwise
        """
        if self._client is None:
            raise RuntimeError("Redis client not connected")

        result = await self._client.exists(key)
        return bool(result)

    async def get(self, key: str) -> str | None:
        """Get a value by key.

        Args:
            key: Redis key

        Returns:
            Value or None if not found
        """
        if self._client is None:
            raise RuntimeError("Redis client not connected")

        return await self._client.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set a value.

        Args:
            key: Redis key
            value: Value to set
            ex: Optional expiration in seconds

        Returns:
            True if successful
        """
        if self._client is None:
            raise RuntimeError("Redis client not connected")

        await self._client.set(key, value, ex=ex)
        return True

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        """Set multiple fields in a hash.

        Args:
            key: Redis key
            mapping: Field-value mapping

        Returns:
            Number of fields added
        """
        if self._client is None:
            raise RuntimeError("Redis client not connected")

        return await self._client.hset(key, mapping=mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        """Get all fields in a hash.

        Args:
            key: Redis key

        Returns:
            Dict of field-value pairs
        """
        if self._client is None:
            raise RuntimeError("Redis client not connected")

        return await self._client.hgetall(key)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on a key.

        Args:
            key: Redis key
            seconds: TTL in seconds

        Returns:
            True if timeout was set
        """
        if self._client is None:
            raise RuntimeError("Redis client not connected")

        return await self._client.expire(key, seconds)

    async def delete(self, key: str) -> int:
        """Delete a key.

        Args:
            key: Redis key

        Returns:
            Number of keys deleted
        """
        if self._client is None:
            raise RuntimeError("Redis client not connected")

        return await self._client.delete(key)
