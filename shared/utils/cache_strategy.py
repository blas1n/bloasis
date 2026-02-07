"""
Redis caching strategy for BLOASIS services.

Provides a unified caching strategy across all tiers:
- Tier 1 (Shared): Market regime, sector data (6h-24h TTL)
- Tier 2 (Shared): OHLCV data, stock info (5min-24h TTL)
- Tier 3 (User-specific): Preferences, portfolio (5min-1h TTL)

Cache Key Naming Convention:
- Tier 1: market:{type}:{key}
- Tier 2: data:{symbol}:{type}
- Tier 3: user:{user_id}:{type}

Usage:
    from shared.utils.cache_strategy import CacheManager, create_cache_manager

    cache = await create_cache_manager("redis://localhost:6379")

    # Using predefined configs
    await cache.set("regime", {"regime": "bull", "confidence": 0.95})
    regime = await cache.get("regime")

    # With cache warming
    regime = await cache.get_or_set(
        "regime",
        fetch_func=lambda: get_regime_from_api(),
    )

    # User-specific with kwargs
    await cache.set("portfolio", portfolio_data, user_id="user-123")
"""

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, TypeVar

from prometheus_client import Counter

from .redis_client import RedisClient

logger = logging.getLogger(__name__)

# Type variable for generic fetch functions
T = TypeVar("T")


# =============================================================================
# Cache Metrics
# =============================================================================

cache_hits_total = Counter(
    "cache_hits_total",
    "Total number of cache hits",
    ["config_name", "tier"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total number of cache misses",
    ["config_name", "tier"],
)

cache_operations_total = Counter(
    "cache_operations_total",
    "Total number of cache operations",
    ["operation", "config_name", "tier"],
)


# =============================================================================
# Cache Tier Enum
# =============================================================================


class CacheTier(str, Enum):
    """Cache tier definitions.

    Tier 1 (TIER1_SHARED): Market-level shared data
    Tier 2 (TIER2_DATA): Symbol-specific shared data
    Tier 3 (TIER3_USER): User-specific data
    """

    TIER1_SHARED = "market"
    TIER2_DATA = "data"
    TIER3_USER = "user"


# =============================================================================
# Cache Configuration
# =============================================================================


@dataclass(frozen=True)
class CacheConfig:
    """Cache configuration for a specific data type.

    Attributes:
        tier: The cache tier (determines key prefix)
        ttl_seconds: Time-to-live in seconds
        key_template: Template for cache key (uses format strings)
    """

    tier: CacheTier
    ttl_seconds: int
    key_template: str


# Predefined cache configurations
CACHE_CONFIGS: dict[str, CacheConfig] = {
    # Tier 1: Market-level shared data
    "regime": CacheConfig(
        tier=CacheTier.TIER1_SHARED,
        ttl_seconds=21600,  # 6 hours
        key_template="market:regime:current",
    ),
    "sector": CacheConfig(
        tier=CacheTier.TIER1_SHARED,
        ttl_seconds=86400,  # 24 hours
        key_template="market:sector:{sector}",
    ),
    "sector_analysis": CacheConfig(
        tier=CacheTier.TIER1_SHARED,
        ttl_seconds=21600,  # 6 hours
        key_template="market:sector:{regime}:analysis",
    ),
    # Tier 2: Symbol-specific shared data
    "ohlcv": CacheConfig(
        tier=CacheTier.TIER2_DATA,
        ttl_seconds=300,  # 5 minutes
        key_template="data:{symbol}:ohlcv",
    ),
    "ohlcv_daily": CacheConfig(
        tier=CacheTier.TIER2_DATA,
        ttl_seconds=300,  # 5 minutes
        key_template="data:{symbol}:ohlcv:daily",
    ),
    "stock_info": CacheConfig(
        tier=CacheTier.TIER2_DATA,
        ttl_seconds=86400,  # 24 hours
        key_template="data:{symbol}:info",
    ),
    "sentiment": CacheConfig(
        tier=CacheTier.TIER2_DATA,
        ttl_seconds=3600,  # 1 hour
        key_template="data:{symbol}:sentiment",
    ),
    "candidates": CacheConfig(
        tier=CacheTier.TIER2_DATA,
        ttl_seconds=21600,  # 6 hours
        key_template="data:candidates:{regime}",
    ),
    # Tier 3: User-specific data
    "preferences": CacheConfig(
        tier=CacheTier.TIER3_USER,
        ttl_seconds=3600,  # 1 hour
        key_template="user:{user_id}:preferences",
    ),
    "portfolio": CacheConfig(
        tier=CacheTier.TIER3_USER,
        ttl_seconds=300,  # 5 minutes
        key_template="user:{user_id}:portfolio",
    ),
    "strategy": CacheConfig(
        tier=CacheTier.TIER3_USER,
        ttl_seconds=3600,  # 1 hour
        key_template="user:{user_id}:strategy",
    ),
    "positions": CacheConfig(
        tier=CacheTier.TIER3_USER,
        ttl_seconds=300,  # 5 minutes
        key_template="user:{user_id}:positions",
    ),
}


# =============================================================================
# JSON Encoder for Decimal Support
# =============================================================================


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def _serialize(value: Any) -> str:
    """Serialize value to JSON string with Decimal support.

    Args:
        value: Value to serialize

    Returns:
        JSON string representation
    """
    return json.dumps(value, cls=DecimalEncoder, default=str)


def _deserialize(data: str) -> Any:
    """Deserialize JSON string to Python object.

    Args:
        data: JSON string

    Returns:
        Deserialized Python object
    """
    return json.loads(data)


# =============================================================================
# Cache Manager
# =============================================================================


class CacheManager:
    """Unified cache manager for BLOASIS services.

    Provides a consistent interface for caching operations across all tiers
    with support for:
    - Predefined cache configurations
    - Automatic key generation from templates
    - TTL management
    - Cache warming and get-or-set patterns
    - Pattern-based invalidation
    - Metrics tracking

    Example:
        cache = CacheManager(redis_client)

        # Set with config name
        await cache.set("regime", {"regime": "bull", "confidence": 0.95})

        # Get with automatic key generation
        regime = await cache.get("regime")

        # Get-or-set pattern with fetch function
        portfolio = await cache.get_or_set(
            "portfolio",
            fetch_func=lambda: fetch_portfolio(user_id),
            user_id="user-123",
        )
    """

    def __init__(self, redis_client: RedisClient) -> None:
        """Initialize cache manager with Redis client.

        Args:
            redis_client: Connected RedisClient instance
        """
        self._redis = redis_client
        self._configs = CACHE_CONFIGS.copy()

    def _get_config(self, config_name: str) -> CacheConfig:
        """Get cache configuration by name.

        Args:
            config_name: Name of the cache configuration

        Returns:
            CacheConfig instance

        Raises:
            ValueError: If config_name is not found
        """
        if config_name not in self._configs:
            raise ValueError(
                f"Unknown cache config: {config_name}. "
                f"Available: {list(self._configs.keys())}"
            )
        return self._configs[config_name]

    def _get_key(self, config_name: str, **kwargs: Any) -> str:
        """Generate cache key from config template and kwargs.

        Args:
            config_name: Name of the cache configuration
            **kwargs: Template variables for key generation

        Returns:
            Formatted cache key string

        Raises:
            ValueError: If required template variables are missing
        """
        config = self._get_config(config_name)
        try:
            return config.key_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(
                f"Missing required key parameter for {config_name}: {e}. "
                f"Template: {config.key_template}"
            ) from e

    def register_config(self, name: str, config: CacheConfig) -> None:
        """Register a custom cache configuration.

        Args:
            name: Configuration name
            config: CacheConfig instance
        """
        self._configs[name] = config
        logger.debug(f"Registered cache config: {name}")

    async def get(self, config_name: str, **kwargs: Any) -> Optional[Any]:
        """Get value from cache.

        Args:
            config_name: Name of the cache configuration
            **kwargs: Template variables for key generation

        Returns:
            Cached value or None if not found
        """
        config = self._get_config(config_name)
        key = self._get_key(config_name, **kwargs)

        try:
            value = await self._redis.get(key)

            if value is not None:
                cache_hits_total.labels(
                    config_name=config_name,
                    tier=config.tier.value,
                ).inc()
                cache_operations_total.labels(
                    operation="get_hit",
                    config_name=config_name,
                    tier=config.tier.value,
                ).inc()
                logger.debug(f"Cache HIT: {key}")
                return value

            cache_misses_total.labels(
                config_name=config_name,
                tier=config.tier.value,
            ).inc()
            cache_operations_total.labels(
                operation="get_miss",
                config_name=config_name,
                tier=config.tier.value,
            ).inc()
            logger.debug(f"Cache MISS: {key}")
            return None

        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return None

    async def set(
        self,
        config_name: str,
        value: Any,
        ttl_override: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Set value in cache.

        Args:
            config_name: Name of the cache configuration
            value: Value to cache
            ttl_override: Optional TTL override in seconds
            **kwargs: Template variables for key generation
        """
        config = self._get_config(config_name)
        key = self._get_key(config_name, **kwargs)
        ttl = ttl_override if ttl_override is not None else config.ttl_seconds

        try:
            # Serialize value
            serialized = _serialize(value)
            await self._redis.setex(key, ttl, serialized)

            cache_operations_total.labels(
                operation="set",
                config_name=config_name,
                tier=config.tier.value,
            ).inc()
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")

        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")
            raise

    async def invalidate(self, config_name: str, **kwargs: Any) -> None:
        """Invalidate a specific cache entry.

        Args:
            config_name: Name of the cache configuration
            **kwargs: Template variables for key generation
        """
        config = self._get_config(config_name)
        key = self._get_key(config_name, **kwargs)

        try:
            await self._redis.delete(key)

            cache_operations_total.labels(
                operation="invalidate",
                config_name=config_name,
                tier=config.tier.value,
            ).inc()
            logger.debug(f"Cache INVALIDATE: {key}")

        except Exception as e:
            logger.error(f"Cache invalidate error for {key}: {e}")
            raise

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern.

        Warning: KEYS command can be slow on large datasets.
        Use with caution in production.

        Args:
            pattern: Redis key pattern (e.g., "market:*", "user:123:*")

        Returns:
            Number of keys deleted
        """
        try:
            if self._redis.client is None:
                raise ConnectionError("Redis client is not connected")

            keys = await self._redis.client.keys(pattern)
            if not keys:
                logger.debug(f"No keys found for pattern: {pattern}")
                return 0

            deleted = await self._redis.client.delete(*keys)
            cache_operations_total.labels(
                operation="invalidate_pattern",
                config_name="pattern",
                tier="all",
            ).inc()
            logger.info(f"Invalidated {deleted} keys matching pattern: {pattern}")
            return deleted

        except Exception as e:
            logger.error(f"Cache invalidate pattern error for {pattern}: {e}")
            raise

    async def warm_cache(
        self,
        config_name: str,
        fetch_func: Callable[[], Awaitable[T]],
        **kwargs: Any,
    ) -> T:
        """Warm cache by fetching and storing data.

        Unconditionally fetches data and stores it in cache.
        Use for pre-populating cache entries.

        Args:
            config_name: Name of the cache configuration
            fetch_func: Async function to fetch data
            **kwargs: Template variables for key generation

        Returns:
            Fetched value
        """
        value = await fetch_func()
        await self.set(config_name, value, **kwargs)

        cache_operations_total.labels(
            operation="warm",
            config_name=config_name,
            tier=self._get_config(config_name).tier.value,
        ).inc()
        logger.debug(f"Cache WARM: {config_name}")

        return value

    async def get_or_set(
        self,
        config_name: str,
        fetch_func: Callable[[], Awaitable[T]],
        ttl_override: Optional[int] = None,
        **kwargs: Any,
    ) -> T:
        """Get value from cache or fetch and store if not present.

        This is the recommended pattern for most cache operations.
        It handles cache misses automatically by calling the fetch function.

        Args:
            config_name: Name of the cache configuration
            fetch_func: Async function to fetch data on cache miss
            ttl_override: Optional TTL override in seconds
            **kwargs: Template variables for key generation

        Returns:
            Cached or freshly fetched value
        """
        # Try to get from cache
        cached = await self.get(config_name, **kwargs)
        if cached is not None:
            return cached

        # Fetch and store
        value = await fetch_func()
        await self.set(config_name, value, ttl_override=ttl_override, **kwargs)

        return value

    async def get_ttl(self, config_name: str, **kwargs: Any) -> Optional[int]:
        """Get remaining TTL for a cache entry.

        Args:
            config_name: Name of the cache configuration
            **kwargs: Template variables for key generation

        Returns:
            Remaining TTL in seconds, or None if key doesn't exist
        """
        key = self._get_key(config_name, **kwargs)

        try:
            if self._redis.client is None:
                raise ConnectionError("Redis client is not connected")

            ttl = await self._redis.client.ttl(key)
            # TTL returns -2 if key doesn't exist, -1 if no TTL set
            if ttl < 0:
                return None
            return ttl

        except Exception as e:
            logger.error(f"Cache get_ttl error for {key}: {e}")
            return None

    async def exists(self, config_name: str, **kwargs: Any) -> bool:
        """Check if a cache entry exists.

        Args:
            config_name: Name of the cache configuration
            **kwargs: Template variables for key generation

        Returns:
            True if key exists, False otherwise
        """
        key = self._get_key(config_name, **kwargs)

        try:
            if self._redis.client is None:
                raise ConnectionError("Redis client is not connected")

            result = await self._redis.client.exists(key)
            return bool(result)

        except Exception as e:
            logger.error(f"Cache exists error for {key}: {e}")
            return False

    async def refresh_ttl(self, config_name: str, **kwargs: Any) -> bool:
        """Refresh TTL for an existing cache entry.

        Resets the TTL to the configured value without changing the data.

        Args:
            config_name: Name of the cache configuration
            **kwargs: Template variables for key generation

        Returns:
            True if TTL was refreshed, False if key doesn't exist
        """
        config = self._get_config(config_name)
        key = self._get_key(config_name, **kwargs)

        try:
            if self._redis.client is None:
                raise ConnectionError("Redis client is not connected")

            result = await self._redis.client.expire(key, config.ttl_seconds)

            if result:
                logger.debug(f"Cache TTL REFRESH: {key} (TTL: {config.ttl_seconds}s)")
            return bool(result)

        except Exception as e:
            logger.error(f"Cache refresh_ttl error for {key}: {e}")
            return False


# =============================================================================
# Factory Function
# =============================================================================


async def create_cache_manager(redis_url: str) -> CacheManager:
    """Create and initialize a CacheManager with a Redis connection.

    Convenience factory function that handles Redis connection setup.

    Args:
        redis_url: Redis URL (e.g., "redis://localhost:6379")
                   Note: Currently uses host/port parsing, not full URL

    Returns:
        Initialized CacheManager instance

    Example:
        cache = await create_cache_manager("redis://localhost:6379")
        await cache.set("regime", {"regime": "bull"})
    """
    # Parse URL to extract host and port
    # Format: redis://host:port or redis://host
    url = redis_url.replace("redis://", "")
    parts = url.split(":")
    host = parts[0] if parts[0] else "localhost"
    port = int(parts[1]) if len(parts) > 1 else 6379

    redis_client = RedisClient(host=host, port=port)
    await redis_client.connect()

    logger.info(f"Created CacheManager connected to {host}:{port}")
    return CacheManager(redis_client)
