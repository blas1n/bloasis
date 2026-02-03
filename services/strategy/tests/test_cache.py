"""Unit tests for Layer 3 cache manager."""

import json
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as redis

from src.utils.cache import (
    UserCacheManager,
    build_preferences_cache_key,
    build_strategy_cache_key,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_mock = AsyncMock(spec=redis.Redis)
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.aclose = AsyncMock()
    return redis_mock


@pytest.fixture
async def cache_manager(mock_redis):
    """Create cache manager with mocked Redis."""
    with patch("src.utils.cache.redis.Redis", return_value=mock_redis):
        manager = UserCacheManager()
        await manager.connect()
        return manager


def test_build_strategy_cache_key():
    """Test strategy cache key generation."""
    user_id = "test_user"
    key = build_strategy_cache_key(user_id)
    assert key == "user:test_user:strategy"


def test_build_preferences_cache_key():
    """Test preferences cache key generation."""
    user_id = "test_user"
    key = build_preferences_cache_key(user_id)
    assert key == "user:test_user:preferences"


@pytest.mark.asyncio
async def test_connect_success(mock_redis):
    """Test successful Redis connection."""
    with patch("src.utils.cache.redis.Redis", return_value=mock_redis):
        manager = UserCacheManager()
        await manager.connect()

        assert manager.connected is True
        mock_redis.ping.assert_called_once()


@pytest.mark.asyncio
async def test_connect_failure(mock_redis):
    """Test Redis connection failure."""
    mock_redis.ping = AsyncMock(side_effect=redis.RedisError("Connection failed"))

    with patch("src.utils.cache.redis.Redis", return_value=mock_redis):
        manager = UserCacheManager()

        with pytest.raises(ConnectionError):
            await manager.connect()


@pytest.mark.asyncio
async def test_connect_already_connected(cache_manager, mock_redis):
    """Test connecting when already connected."""
    # Try to connect again
    await cache_manager.connect()

    # Ping should only be called once (from fixture)
    assert mock_redis.ping.call_count == 1


@pytest.mark.asyncio
async def test_get_cache_hit(cache_manager, mock_redis):
    """Test cache GET with cache hit."""
    key = "test_key"
    expected_data = {"test": "data"}

    mock_redis.get = AsyncMock(return_value=json.dumps(expected_data))

    result = await cache_manager.get(key)

    assert result == expected_data
    mock_redis.get.assert_called_once_with(key)


@pytest.mark.asyncio
async def test_get_cache_miss(cache_manager, mock_redis):
    """Test cache GET with cache miss."""
    key = "test_key"

    mock_redis.get = AsyncMock(return_value=None)

    result = await cache_manager.get(key)

    assert result is None
    mock_redis.get.assert_called_once_with(key)


@pytest.mark.asyncio
async def test_get_redis_error(cache_manager, mock_redis):
    """Test cache GET with Redis error."""
    key = "test_key"

    mock_redis.get = AsyncMock(side_effect=redis.RedisError("Connection error"))

    result = await cache_manager.get(key)

    # Should return None on error (graceful degradation)
    assert result is None


@pytest.mark.asyncio
async def test_set_success(cache_manager, mock_redis):
    """Test cache SET success."""
    key = "test_key"
    value = {"test": "data"}
    ttl = 3600

    result = await cache_manager.set(key, value, ttl)

    assert result is True
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    assert call_args[0][0] == key
    assert call_args[0][1] == ttl


@pytest.mark.asyncio
async def test_set_default_ttl(cache_manager, mock_redis):
    """Test cache SET with default TTL."""
    key = "test_key"
    value = {"test": "data"}

    result = await cache_manager.set(key, value)

    assert result is True
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_set_redis_error(cache_manager, mock_redis):
    """Test cache SET with Redis error."""
    key = "test_key"
    value = {"test": "data"}

    mock_redis.setex = AsyncMock(side_effect=redis.RedisError("Connection error"))

    result = await cache_manager.set(key, value)

    # Should return False on error
    assert result is False


@pytest.mark.asyncio
async def test_set_with_default_str_conversion(cache_manager, mock_redis):
    """Test cache SET with values that need str conversion."""
    from datetime import datetime

    key = "test_key"
    # datetime needs default=str in json.dumps
    value = {"timestamp": datetime.now()}

    result = await cache_manager.set(key, value)

    # Should succeed with default=str
    assert result is True


@pytest.mark.asyncio
async def test_delete_success(cache_manager, mock_redis):
    """Test cache DELETE success."""
    key = "test_key"

    mock_redis.delete = AsyncMock(return_value=1)

    result = await cache_manager.delete(key)

    assert result is True
    mock_redis.delete.assert_called_once_with(key)


@pytest.mark.asyncio
async def test_delete_key_not_found(cache_manager, mock_redis):
    """Test cache DELETE when key doesn't exist."""
    key = "test_key"

    mock_redis.delete = AsyncMock(return_value=0)

    result = await cache_manager.delete(key)

    assert result is False


@pytest.mark.asyncio
async def test_delete_redis_error(cache_manager, mock_redis):
    """Test cache DELETE with Redis error."""
    key = "test_key"

    mock_redis.delete = AsyncMock(side_effect=redis.RedisError("Connection error"))

    result = await cache_manager.delete(key)

    assert result is False


@pytest.mark.asyncio
async def test_invalidate_user_success(cache_manager, mock_redis):
    """Test invalidating all user cache entries."""
    user_id = "test_user"
    keys = ["user:test_user:strategy", "user:test_user:preferences"]

    mock_redis.keys = AsyncMock(return_value=keys)
    mock_redis.delete = AsyncMock(return_value=len(keys))

    result = await cache_manager.invalidate_user(user_id)

    assert result == len(keys)
    mock_redis.keys.assert_called_once_with("user:test_user:*")
    mock_redis.delete.assert_called_once_with(*keys)


@pytest.mark.asyncio
async def test_invalidate_user_no_keys(cache_manager, mock_redis):
    """Test invalidating user when no cache entries exist."""
    user_id = "test_user"

    mock_redis.keys = AsyncMock(return_value=[])

    result = await cache_manager.invalidate_user(user_id)

    assert result == 0
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_invalidate_user_redis_error(cache_manager, mock_redis):
    """Test invalidate user with Redis error."""
    user_id = "test_user"

    mock_redis.keys = AsyncMock(side_effect=redis.RedisError("Connection error"))

    result = await cache_manager.invalidate_user(user_id)

    assert result == 0


@pytest.mark.asyncio
async def test_close(cache_manager, mock_redis):
    """Test closing Redis connection."""
    await cache_manager.close()

    assert cache_manager.redis is None
    assert cache_manager.connected is False
    mock_redis.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_get_without_connect():
    """Test GET auto-connects if not connected."""
    mock_redis = AsyncMock(spec=redis.Redis)
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)

    with patch("src.utils.cache.redis.Redis", return_value=mock_redis):
        manager = UserCacheManager()

        # Call get without explicit connect
        await manager.get("test_key")

        # Should auto-connect
        assert manager.connected is True
        mock_redis.ping.assert_called_once()
