"""Redis caching utility for Classification Service.

Layer 2 caching: Shared across all users with 6-hour TTL.
"""

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from ..config import config

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis cache manager for Layer 2 (shared) caching."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        ttl: Optional[int] = None,
    ):
        """Initialize cache manager.

        Args:
            host: Redis host (default from config)
            port: Redis port (default from config)
            ttl: Default TTL in seconds (default 6 hours from config)
        """
        self.host = host or config.redis_host
        self.port = port or config.redis_port
        self.default_ttl = ttl or config.cache_ttl

        self.redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis server."""
        if self.redis:
            logger.warning("Redis already connected")
            return

        self.redis = redis.Redis(
            host=self.host,
            port=self.port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )

        # Test connection
        await self.redis.ping()
        logger.info(f"Connected to Redis at {self.host}:{self.port}")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value (deserialized from JSON) or None if not found
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None, "redis should be initialized after connect()"

        try:
            data = await self.redis.get(key)
            if data:
                logger.debug(f"Cache hit: {key}")
                return json.loads(data)

            logger.debug(f"Cache miss: {key}")
            return None

        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: TTL in seconds (default from config)

        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None, "redis should be initialized after connect()"

        ttl = ttl or self.default_ttl

        try:
            serialized = json.dumps(value, default=str)
            await self.redis.setex(key, ttl, serialized)
            logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
            return True

        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if key existed and was deleted, False otherwise
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None, "redis should be initialized after connect()"

        try:
            result = await self.redis.delete(key)
            logger.debug(f"Cache delete: {key} (existed: {result > 0})")
            return result > 0

        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern.

        Useful for regime changes: invalidate all sector/theme caches.

        Args:
            pattern: Redis key pattern (e.g., "sectors:*")

        Returns:
            Number of keys deleted
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None, "redis should be initialized after connect()"

        try:
            keys = await self.redis.keys(pattern)
            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(f"Invalidated {deleted} keys matching pattern: {pattern}")
                return deleted

            logger.debug(f"No keys found for pattern: {pattern}")
            return 0

        except Exception as e:
            logger.error(f"Cache invalidate pattern error for {pattern}: {e}")
            return 0

    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.aclose()
            self.redis = None
            logger.info("Redis connection closed")


def build_sector_cache_key(regime: str) -> str:
    """Build cache key for sector analysis.

    Args:
        regime: Market regime

    Returns:
        Cache key (e.g., "sectors:bull:analysis")
    """
    return f"sectors:{regime}:analysis"


def build_theme_cache_key(sectors: list[str], regime: str) -> str:
    """Build cache key for thematic analysis.

    Args:
        sectors: Selected sectors (will be sorted for consistent key)
        regime: Market regime

    Returns:
        Cache key (e.g., "themes:bull:Technology:Healthcare:Financials")
    """
    sorted_sectors = ":".join(sorted(sectors))
    return f"themes:{regime}:{sorted_sectors}"


def build_candidate_cache_key(regime: str) -> str:
    """Build cache key for candidate symbols.

    Args:
        regime: Market regime

    Returns:
        Cache key (e.g., "candidates:bull")
    """
    return f"candidates:{regime}"
