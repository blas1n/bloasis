"""Unit tests for cache utility."""

from unittest.mock import AsyncMock, patch

import pytest

from src.utils.cache import (
    CacheManager,
    build_candidate_cache_key,
    build_sector_cache_key,
    build_theme_cache_key,
)


@pytest.mark.asyncio
class TestCacheManager:
    """Test CacheManager."""

    async def test_connect(self):
        """Test connection to Redis."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis_class.return_value = mock_redis

            await cache.connect()

            assert cache.redis is not None
            mock_redis.ping.assert_called_once()

    async def test_get_hit(self):
        """Test cache get with hit."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.get = AsyncMock(return_value='{"key": "value"}')
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            result = await cache.get("test_key")

            assert result == {"key": "value"}
            mock_redis.get.assert_called_once_with("test_key")

    async def test_get_miss(self):
        """Test cache get with miss."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            result = await cache.get("missing_key")

            assert result is None

    async def test_set(self):
        """Test cache set."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.setex = AsyncMock()
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            result = await cache.set("test_key", {"data": "value"}, ttl=3600)

            assert result is True
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            assert call_args[0] == "test_key"
            assert call_args[1] == 3600

    async def test_delete(self):
        """Test cache delete."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.delete = AsyncMock(return_value=1)
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            result = await cache.delete("test_key")

            assert result is True
            mock_redis.delete.assert_called_once_with("test_key")

    async def test_invalidate_pattern(self):
        """Test pattern-based invalidation."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.keys = AsyncMock(return_value=["key1", "key2", "key3"])
            mock_redis.delete = AsyncMock(return_value=3)
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            count = await cache.invalidate_pattern("sectors:*")

            assert count == 3
            mock_redis.keys.assert_called_once_with("sectors:*")
            mock_redis.delete.assert_called_once_with("key1", "key2", "key3")

    async def test_invalidate_pattern_no_keys(self):
        """Test pattern invalidation when no keys match."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.keys = AsyncMock(return_value=[])
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            count = await cache.invalidate_pattern("nonexistent:*")

            assert count == 0

    async def test_close(self):
        """Test closing Redis connection."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            await cache.close()

            assert cache.redis is None
            mock_redis.aclose.assert_called_once()

    async def test_get_error_handling(self):
        """Test error handling in get."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            result = await cache.get("test_key")

            # Should return None on error, not raise
            assert result is None

    async def test_set_error_handling(self):
        """Test error handling in set."""
        cache = CacheManager()

        with patch("src.utils.cache.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
            mock_redis_class.return_value = mock_redis

            await cache.connect()
            result = await cache.set("test_key", {"data": "value"})

            # Should return False on error, not raise
            assert result is False


class TestCacheKeyBuilders:
    """Test cache key builder functions."""

    def test_build_sector_cache_key(self):
        """Test sector cache key builder."""
        key = build_sector_cache_key("bull")
        assert key == "sectors:bull:analysis"

    def test_build_theme_cache_key(self):
        """Test theme cache key builder."""
        # Should sort sectors for consistent key
        key1 = build_theme_cache_key(["Technology", "Healthcare"], "bull")
        key2 = build_theme_cache_key(["Healthcare", "Technology"], "bull")

        assert key1 == key2
        assert "Technology" in key1
        assert "Healthcare" in key1
        assert "bull" in key1

    def test_build_candidate_cache_key(self):
        """Test candidate cache key builder."""
        key = build_candidate_cache_key("crisis")
        assert key == "candidates:crisis"
