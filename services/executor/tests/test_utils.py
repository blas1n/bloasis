"""Tests for Executor Service Utilities."""

from unittest.mock import AsyncMock, patch

import pytest

from src.utils.event_publisher import EventPublisher
from src.utils.redis_client import RedisClient


class TestEventPublisher:
    """Tests for EventPublisher."""

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connecting to Redpanda."""
        with patch("src.utils.event_publisher.AIOKafkaProducer") as mock_producer_class:
            mock_producer = AsyncMock()
            mock_producer_class.return_value = mock_producer

            publisher = EventPublisher()
            await publisher.connect()

            mock_producer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_existing_producer(self):
        """Test connecting when producer already exists."""
        mock_producer = AsyncMock()

        publisher = EventPublisher(producer=mock_producer)
        await publisher.connect()

        mock_producer.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing Redpanda connection."""
        mock_producer = AsyncMock()

        publisher = EventPublisher(producer=mock_producer)
        await publisher.close()

        mock_producer.stop.assert_called_once()
        assert publisher._producer is None

    @pytest.mark.asyncio
    async def test_close_not_connected(self):
        """Test closing when not connected."""
        publisher = EventPublisher()

        await publisher.close()

    @pytest.mark.asyncio
    async def test_publish_order_executed(self):
        """Test publishing order executed event."""
        mock_producer = AsyncMock()

        publisher = EventPublisher(producer=mock_producer)

        await publisher.publish_order_executed(
            user_id="test-user",
            order_id="order-123",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            status="filled",
            filled_qty=10.0,
            filled_price=175.50,
        )

        mock_producer.send_and_wait.assert_called_once()
        call_args = mock_producer.send_and_wait.call_args

        assert call_args[0][0] == "order-executed"
        assert call_args[1]["key"] == b"test-user"

        event = call_args[1]["value"]
        assert event["event_type"] == "order_executed"
        assert event["user_id"] == "test-user"
        assert event["order_id"] == "order-123"
        assert event["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_publish_order_executed_not_connected(self):
        """Test publishing when not connected."""
        publisher = EventPublisher()

        with patch("src.utils.event_publisher.logger") as mock_logger:
            await publisher.publish_order_executed(
                user_id="test-user",
                order_id="order-123",
                symbol="AAPL",
                side="buy",
                qty=10.0,
                status="filled",
                filled_qty=10.0,
                filled_price=175.50,
            )

            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_order_executed_error(self):
        """Test publishing with error."""
        mock_producer = AsyncMock()
        mock_producer.send_and_wait.side_effect = Exception("Connection error")

        publisher = EventPublisher(producer=mock_producer)

        with pytest.raises(Exception, match="Connection error"):
            await publisher.publish_order_executed(
                user_id="test-user",
                order_id="order-123",
                symbol="AAPL",
                side="buy",
                qty=10.0,
                status="filled",
                filled_qty=10.0,
                filled_price=175.50,
            )

    @pytest.mark.asyncio
    async def test_publish_order_cancelled(self):
        """Test publishing order cancelled event."""
        mock_producer = AsyncMock()

        publisher = EventPublisher(producer=mock_producer)

        await publisher.publish_order_cancelled(
            user_id="test-user",
            order_id="order-123",
        )

        mock_producer.send_and_wait.assert_called_once()
        call_args = mock_producer.send_and_wait.call_args

        assert call_args[0][0] == "order-cancelled"
        assert call_args[1]["key"] == b"test-user"

        event = call_args[1]["value"]
        assert event["event_type"] == "order_cancelled"
        assert event["user_id"] == "test-user"
        assert event["order_id"] == "order-123"

    @pytest.mark.asyncio
    async def test_publish_order_cancelled_not_connected(self):
        """Test publishing cancelled when not connected."""
        publisher = EventPublisher()

        with patch("src.utils.event_publisher.logger") as mock_logger:
            await publisher.publish_order_cancelled(
                user_id="test-user",
                order_id="order-123",
            )

            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_order_cancelled_error(self):
        """Test publishing cancelled with error."""
        mock_producer = AsyncMock()
        mock_producer.send_and_wait.side_effect = Exception("Connection error")

        publisher = EventPublisher(producer=mock_producer)

        with pytest.raises(Exception, match="Connection error"):
            await publisher.publish_order_cancelled(
                user_id="test-user",
                order_id="order-123",
            )


class TestRedisClient:
    """Tests for RedisClient."""

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connecting to Redis."""
        with patch("src.utils.redis_client.redis.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.return_value = mock_client

            client = RedisClient(host="localhost", port=6379)
            await client.connect()

            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_existing_client(self):
        """Test connecting when client already exists."""
        mock_client = AsyncMock()

        client = RedisClient(client=mock_client)
        await client.connect()

        mock_client.ping.assert_not_called()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing Redis connection."""
        mock_client = AsyncMock()

        client = RedisClient(client=mock_client)
        await client.close()

        mock_client.aclose.assert_called_once()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_not_connected(self):
        """Test closing when not connected."""
        client = RedisClient()

        await client.close()

    @pytest.mark.asyncio
    async def test_exists_true(self):
        """Test checking if key exists."""
        mock_client = AsyncMock()
        mock_client.exists.return_value = 1

        client = RedisClient(client=mock_client)
        result = await client.exists("test-key")

        assert result is True
        mock_client.exists.assert_called_once_with("test-key")

    @pytest.mark.asyncio
    async def test_exists_false(self):
        """Test checking if key does not exist."""
        mock_client = AsyncMock()
        mock_client.exists.return_value = 0

        client = RedisClient(client=mock_client)
        result = await client.exists("test-key")

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_not_connected(self):
        """Test exists when not connected."""
        client = RedisClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.exists("test-key")

    @pytest.mark.asyncio
    async def test_get(self):
        """Test getting a value."""
        mock_client = AsyncMock()
        mock_client.get.return_value = "test-value"

        client = RedisClient(client=mock_client)
        result = await client.get("test-key")

        assert result == "test-value"
        mock_client.get.assert_called_once_with("test-key")

    @pytest.mark.asyncio
    async def test_get_none(self):
        """Test getting a non-existent value."""
        mock_client = AsyncMock()
        mock_client.get.return_value = None

        client = RedisClient(client=mock_client)
        result = await client.get("test-key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_not_connected(self):
        """Test get when not connected."""
        client = RedisClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.get("test-key")

    @pytest.mark.asyncio
    async def test_set(self):
        """Test setting a value."""
        mock_client = AsyncMock()

        client = RedisClient(client=mock_client)
        result = await client.set("test-key", "test-value")

        assert result is True
        mock_client.set.assert_called_once_with("test-key", "test-value", ex=None)

    @pytest.mark.asyncio
    async def test_set_with_expiration(self):
        """Test setting a value with expiration."""
        mock_client = AsyncMock()

        client = RedisClient(client=mock_client)
        result = await client.set("test-key", "test-value", ex=3600)

        assert result is True
        mock_client.set.assert_called_once_with("test-key", "test-value", ex=3600)

    @pytest.mark.asyncio
    async def test_set_not_connected(self):
        """Test set when not connected."""
        client = RedisClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.set("test-key", "test-value")

    @pytest.mark.asyncio
    async def test_hset(self):
        """Test setting hash fields."""
        mock_client = AsyncMock()
        mock_client.hset.return_value = 2

        client = RedisClient(client=mock_client)
        result = await client.hset("test-key", {"field1": "value1", "field2": "value2"})

        assert result == 2
        mock_client.hset.assert_called_once_with(
            "test-key", mapping={"field1": "value1", "field2": "value2"}
        )

    @pytest.mark.asyncio
    async def test_hset_not_connected(self):
        """Test hset when not connected."""
        client = RedisClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.hset("test-key", {"field": "value"})

    @pytest.mark.asyncio
    async def test_hgetall(self):
        """Test getting all hash fields."""
        mock_client = AsyncMock()
        mock_client.hgetall.return_value = {"field1": "value1", "field2": "value2"}

        client = RedisClient(client=mock_client)
        result = await client.hgetall("test-key")

        assert result == {"field1": "value1", "field2": "value2"}
        mock_client.hgetall.assert_called_once_with("test-key")

    @pytest.mark.asyncio
    async def test_hgetall_not_connected(self):
        """Test hgetall when not connected."""
        client = RedisClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.hgetall("test-key")

    @pytest.mark.asyncio
    async def test_expire(self):
        """Test setting expiration on a key."""
        mock_client = AsyncMock()
        mock_client.expire.return_value = True

        client = RedisClient(client=mock_client)
        result = await client.expire("test-key", 3600)

        assert result is True
        mock_client.expire.assert_called_once_with("test-key", 3600)

    @pytest.mark.asyncio
    async def test_expire_not_connected(self):
        """Test expire when not connected."""
        client = RedisClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.expire("test-key", 3600)

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting a key."""
        mock_client = AsyncMock()
        mock_client.delete.return_value = 1

        client = RedisClient(client=mock_client)
        result = await client.delete("test-key")

        assert result == 1
        mock_client.delete.assert_called_once_with("test-key")

    @pytest.mark.asyncio
    async def test_delete_not_connected(self):
        """Test delete when not connected."""
        client = RedisClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.delete("test-key")
