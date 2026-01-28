"""
Unit tests for RedisClient.

All external dependencies (Redis) are mocked.
"""

from unittest.mock import AsyncMock, patch

import pytest

from shared.utils.redis_client import RedisClient


class TestRedisClientInit:
    """Tests for RedisClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Should use environment variable defaults."""
        with patch.dict("os.environ", {}, clear=True):
            client = RedisClient()
            assert client.host == "redis"
            assert client.port == 6379
            assert client.client is None

    def test_init_with_env_vars(self) -> None:
        """Should read from environment variables."""
        with patch.dict(
            "os.environ", {"REDIS_HOST": "custom-host", "REDIS_PORT": "6380"}
        ):
            client = RedisClient()
            assert client.host == "custom-host"
            assert client.port == 6380

    def test_init_with_explicit_params(self) -> None:
        """Should use explicit parameters over env vars."""
        with patch.dict("os.environ", {"REDIS_HOST": "env-host", "REDIS_PORT": "6380"}):
            client = RedisClient(host="explicit-host", port=9999)
            assert client.host == "explicit-host"
            assert client.port == 9999


class TestRedisClientConnect:
    """Tests for RedisClient.connect()."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Should connect and ping successfully."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("shared.utils.redis_client.redis.Redis", return_value=mock_redis):
            client = RedisClient(host="localhost", port=6379)
            await client.connect()

            assert client.client is mock_redis
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self) -> None:
        """Should raise ConnectionError on failure."""
        from redis.exceptions import RedisError

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RedisError("Connection refused"))

        with patch("shared.utils.redis_client.redis.Redis", return_value=mock_redis):
            client = RedisClient(host="localhost", port=6379)

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            assert "Failed to connect to Redis" in str(exc_info.value)
            assert "localhost:6379" in str(exc_info.value)


class TestRedisClientClose:
    """Tests for RedisClient.close()."""

    @pytest.mark.asyncio
    async def test_close_connected_client(self) -> None:
        """Should close connection and set client to None."""
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        client = RedisClient()
        client.client = mock_redis

        await client.close()

        mock_redis.aclose.assert_called_once()
        assert client.client is None

    @pytest.mark.asyncio
    async def test_close_not_connected(self) -> None:
        """Should handle close when not connected."""
        client = RedisClient()
        client.client = None

        await client.close()  # Should not raise

        assert client.client is None


class TestRedisClientGet:
    """Tests for RedisClient.get()."""

    @pytest.mark.asyncio
    async def test_get_not_connected(self) -> None:
        """Should raise ConnectionError if not connected."""
        client = RedisClient()

        with pytest.raises(ConnectionError) as exc_info:
            await client.get("key")

        assert "not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_key_not_found(self) -> None:
        """Should return None for non-existent key."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        client = RedisClient()
        client.client = mock_redis

        result = await client.get("nonexistent")

        assert result is None
        mock_redis.get.assert_called_once_with("nonexistent")

    @pytest.mark.asyncio
    async def test_get_json_value(self) -> None:
        """Should deserialize JSON values."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"key": "value", "num": 42}')

        client = RedisClient()
        client.client = mock_redis

        result = await client.get("json_key")

        assert result == {"key": "value", "num": 42}

    @pytest.mark.asyncio
    async def test_get_string_value(self) -> None:
        """Should return plain string if not valid JSON."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="plain string value")

        client = RedisClient()
        client.client = mock_redis

        result = await client.get("string_key")

        assert result == "plain string value"

    @pytest.mark.asyncio
    async def test_get_json_list(self) -> None:
        """Should deserialize JSON list values."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='[1, 2, 3, "four"]')

        client = RedisClient()
        client.client = mock_redis

        result = await client.get("list_key")

        assert result == [1, 2, 3, "four"]


class TestRedisClientSetex:
    """Tests for RedisClient.setex()."""

    @pytest.mark.asyncio
    async def test_setex_not_connected(self) -> None:
        """Should raise ConnectionError if not connected."""
        client = RedisClient()

        with pytest.raises(ConnectionError) as exc_info:
            await client.setex("key", 3600, "value")

        assert "not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_setex_dict_value(self) -> None:
        """Should serialize dict to JSON."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        client = RedisClient()
        client.client = mock_redis

        await client.setex("dict_key", 3600, {"foo": "bar"})

        mock_redis.setex.assert_called_once_with("dict_key", 3600, '{"foo": "bar"}')

    @pytest.mark.asyncio
    async def test_setex_list_value(self) -> None:
        """Should serialize list to JSON."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        client = RedisClient()
        client.client = mock_redis

        await client.setex("list_key", 1800, [1, 2, 3])

        mock_redis.setex.assert_called_once_with("list_key", 1800, "[1, 2, 3]")

    @pytest.mark.asyncio
    async def test_setex_string_value(self) -> None:
        """Should store string as-is."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        client = RedisClient()
        client.client = mock_redis

        await client.setex("string_key", 7200, "plain value")

        mock_redis.setex.assert_called_once_with("string_key", 7200, "plain value")

    @pytest.mark.asyncio
    async def test_setex_numeric_value(self) -> None:
        """Should convert numeric values to string."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        client = RedisClient()
        client.client = mock_redis

        await client.setex("num_key", 3600, 12345)

        mock_redis.setex.assert_called_once_with("num_key", 3600, "12345")


class TestRedisClientDelete:
    """Tests for RedisClient.delete()."""

    @pytest.mark.asyncio
    async def test_delete_not_connected(self) -> None:
        """Should raise ConnectionError if not connected."""
        client = RedisClient()

        with pytest.raises(ConnectionError) as exc_info:
            await client.delete("key")

        assert "not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_key(self) -> None:
        """Should delete the key from Redis."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        client = RedisClient()
        client.client = mock_redis

        await client.delete("key_to_delete")

        mock_redis.delete.assert_called_once_with("key_to_delete")
