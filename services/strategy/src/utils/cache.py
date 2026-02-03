"""Layer 3 caching utilities for user-specific data.

Layer 3 caching strategy:
- User-specific cache (per-user keys)
- 1-hour TTL for strategies
- 30-day TTL for preferences
- Cache invalidation on preference updates
"""

import json
import logging
from typing import Any

import redis.asyncio as redis

from ..config import config

logger = logging.getLogger(__name__)


class UserCacheManager:
    """Layer 3 cache manager for user-specific data.

    Handles caching of:
    - User strategies (1-hour TTL)
    - User preferences (30-day TTL)
    """

    def __init__(self):
        """Initialize cache manager with Redis connection."""
        self.redis: redis.Redis | None = None
        self.connected = False

    async def connect(self) -> None:
        """Establish connection to Redis."""
        if self.connected:
            logger.warning("Cache manager already connected")
            return

        self.redis = redis.Redis(
            host=config.redis_host,
            port=config.redis_port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        # Test connection
        try:
            await self.redis.ping()
            self.connected = True
            logger.info(f"Connected to Redis at {config.redis_host}:{config.redis_port}")
        except redis.RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise ConnectionError(f"Redis connection failed: {e}") from e

    async def get(self, key: str) -> Any | None:
        """Retrieve data from cache.

        Args:
            key: Cache key

        Returns:
            Cached data (deserialized from JSON) or None if not found
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None, "redis should be initialized after connect()"

        try:
            data = await self.redis.get(key)
            if data:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(data)

            logger.debug(f"Cache MISS: {key}")
            return None

        except redis.RedisError as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None  # Graceful degradation on cache failure

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Store data in cache.

        Args:
            key: Cache key
            value: Data to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (default: config.cache_ttl)

        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None, "redis should be initialized after connect()"

        ttl = ttl or config.cache_ttl

        try:
            serialized = json.dumps(value, default=str)
            await self.redis.setex(key, ttl, serialized)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True

        except redis.RedisError as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            return False
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete data from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False otherwise
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None, "redis should be initialized after connect()"

        try:
            result = await self.redis.delete(key)
            if result:
                logger.debug(f"Cache DELETE: {key}")
            return bool(result)

        except redis.RedisError as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
            return False

    async def invalidate_user(self, user_id: str) -> int:
        """Invalidate all cache entries for a user.

        Args:
            user_id: User ID

        Returns:
            Number of keys deleted
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None, "redis should be initialized after connect()"

        try:
            pattern = f"user:{user_id}:*"
            keys = await self.redis.keys(pattern)

            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(f"Invalidated {deleted} cache entries for user {user_id}")
                return deleted

            logger.debug(f"No cache entries found for user {user_id}")
            return 0

        except redis.RedisError as e:
            logger.error(f"Redis invalidation error for user {user_id}: {e}")
            return 0

    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.aclose()
            self.redis = None
            self.connected = False
            logger.info("Redis connection closed")


def build_strategy_cache_key(user_id: str) -> str:
    """Build cache key for user strategy.

    Args:
        user_id: User ID

    Returns:
        Cache key for user strategy
    """
    return f"user:{user_id}:strategy"


def build_preferences_cache_key(user_id: str) -> str:
    """Build cache key for user preferences.

    Args:
        user_id: User ID

    Returns:
        Cache key for user preferences
    """
    return f"user:{user_id}:preferences"
