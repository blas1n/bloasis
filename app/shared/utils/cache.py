"""Generic cache-aside helper.

Replaces 5x duplicated cache patterns across services with a single decorator.
"""

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_LOCK_TTL = 30  # seconds — max time to hold a computation lock


def cache_aside(
    key_fn: Callable[..., str],
    ttl: int = 300,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Cache-aside decorator for async methods.

    The decorated method must belong to a class with a `redis` attribute
    (a RedisClient instance).

    Uses a Redis SETNX lock to prevent concurrent cache-miss stampedes
    (e.g., duplicate LLM calls for the same Tier-1 cache key).

    Args:
        key_fn: Function that takes the same args as the decorated method
                and returns the cache key string.
        ttl: Cache TTL in seconds.

    Example:
        @cache_aside(key_fn=lambda self, symbol, period: f"ohlcv:{symbol}:{period}", ttl=300)
        async def get_ohlcv(self, symbol: str, period: str) -> dict:
            return await self._fetch_from_api(symbol, period)
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            redis = getattr(self, "redis", None)
            if redis is None:
                return await func(self, *args, **kwargs)

            cache_key = key_fn(self, *args, **kwargs)

            # Try cache
            try:
                cached = await redis.get(cache_key)
                if cached is not None:
                    return cached
            except OSError as e:
                logger.warning("Cache read error for %s: %s", cache_key, e)

            # Acquire lock to prevent stampede on concurrent cache misses
            lock_key = f"{cache_key}:lock"
            acquired = False
            try:
                if redis.client:
                    acquired = await redis.client.set(lock_key, "1", nx=True, ex=_LOCK_TTL)
            except OSError:
                pass

            if not acquired:
                # Another request is computing — wait briefly, then check cache again
                await asyncio.sleep(1)
                try:
                    cached = await redis.get(cache_key)
                    if cached is not None:
                        return cached
                except OSError:
                    pass
                # Still no cache — fall through and compute anyway

            try:
                result = await func(self, *args, **kwargs)

                # Write to cache
                if result is not None:
                    try:
                        await redis.setex(cache_key, ttl, result)
                    except OSError as e:
                        logger.warning("Cache write error for %s: %s", cache_key, e)

                return result
            finally:
                # Release lock
                if acquired:
                    try:
                        await redis.delete(lock_key)
                    except OSError:
                        pass

        return wrapper

    return decorator
