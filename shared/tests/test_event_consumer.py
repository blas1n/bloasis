"""
Unit tests for EventConsumer.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from shared.utils.event_consumer import EventConsumer


class TestEventConsumer:
    """Tests for EventConsumer class."""

    @pytest.fixture
    def consumer(self) -> EventConsumer:
        """Create an EventConsumer instance."""
        return EventConsumer(
            group_id="test-group",
            topics=["regime-events", "alert-events"],
            brokers="localhost:9092",
        )

    def test_init(self, consumer: EventConsumer) -> None:
        """Test consumer initialization."""
        assert consumer.group_id == "test-group"
        assert consumer.topics == ["regime-events", "alert-events"]
        assert consumer.brokers == "localhost:9092"
        assert consumer._consumer is None
        assert consumer._handlers == {}
        assert not consumer._running

    def test_init_default_brokers(self) -> None:
        """Test default broker from environment."""
        with patch.dict("os.environ", {"REDPANDA_BROKERS": "redpanda:9092"}):
            consumer = EventConsumer(
                group_id="test",
                topics=["test-topic"],
            )
            assert consumer.brokers == "redpanda:9092"

    def test_register_handler(self, consumer: EventConsumer) -> None:
        """Test handler registration."""

        async def handler(event: dict) -> None:
            pass

        consumer.register_handler("regime_change", handler, min_priority=2)

        assert "regime_change" in consumer._handlers
        registered_handler, min_priority = consumer._handlers["regime_change"]
        assert registered_handler == handler
        assert min_priority == 2

    def test_register_handler_default_priority(self, consumer: EventConsumer) -> None:
        """Test handler registration with default priority."""

        async def handler(event: dict) -> None:
            pass

        consumer.register_handler("market_alert", handler)

        _, min_priority = consumer._handlers["market_alert"]
        assert min_priority == 0

    def test_unregister_handler(self, consumer: EventConsumer) -> None:
        """Test handler unregistration."""

        async def handler(event: dict) -> None:
            pass

        consumer.register_handler("regime_change", handler)
        assert "regime_change" in consumer._handlers

        consumer.unregister_handler("regime_change")
        assert "regime_change" not in consumer._handlers

    def test_unregister_nonexistent_handler(self, consumer: EventConsumer) -> None:
        """Test unregistering non-existent handler doesn't raise."""
        consumer.unregister_handler("nonexistent")  # Should not raise

    def test_is_running_property(self, consumer: EventConsumer) -> None:
        """Test is_running property."""
        assert not consumer.is_running

        consumer._running = True
        assert consumer.is_running

    @pytest.mark.asyncio
    async def test_handle_message_calls_handler(self, consumer: EventConsumer) -> None:
        """Test message handling calls registered handler."""
        handler = AsyncMock()
        consumer.register_handler("regime_change", handler, min_priority=0)

        event = {
            "event_type": "regime_change",
            "event_id": "test-123",
            "priority": 2,
            "new_regime": "bear",
        }

        await consumer._handle_message(event)

        handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_handle_message_respects_priority(
        self, consumer: EventConsumer
    ) -> None:
        """Test message handling respects minimum priority."""
        handler = AsyncMock()
        consumer.register_handler("regime_change", handler, min_priority=2)

        # Event with priority below threshold
        low_priority_event = {
            "event_type": "regime_change",
            "event_id": "test-low",
            "priority": 1,  # Below min_priority of 2
        }

        await consumer._handle_message(low_priority_event)
        handler.assert_not_called()

        # Event with priority at threshold
        high_priority_event = {
            "event_type": "regime_change",
            "event_id": "test-high",
            "priority": 2,  # Meets min_priority
        }

        await consumer._handle_message(high_priority_event)
        handler.assert_called_once_with(high_priority_event)

    @pytest.mark.asyncio
    async def test_handle_message_no_handler(self, consumer: EventConsumer) -> None:
        """Test message handling when no handler registered."""
        event = {
            "event_type": "unknown_type",
            "event_id": "test-123",
        }

        # Should not raise
        await consumer._handle_message(event)

    @pytest.mark.asyncio
    async def test_handle_message_handler_error(self, consumer: EventConsumer) -> None:
        """Test message handling continues on handler error."""
        handler = AsyncMock(side_effect=ValueError("Test error"))
        consumer.register_handler("regime_change", handler)

        event = {
            "event_type": "regime_change",
            "event_id": "test-123",
            "priority": 2,
        }

        # Should not raise, just log the error
        await consumer._handle_message(event)
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_default_priority(
        self, consumer: EventConsumer
    ) -> None:
        """Test message handling with missing priority defaults to 0."""
        handler = AsyncMock()
        consumer.register_handler("regime_change", handler, min_priority=0)

        event = {
            "event_type": "regime_change",
            "event_id": "test-123",
            # No priority field
        }

        await consumer._handle_message(event)
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_creates_consumer(self, consumer: EventConsumer) -> None:
        """Test start creates Kafka consumer."""
        mock_kafka_consumer = AsyncMock()

        with patch(
            "shared.utils.event_consumer.AIOKafkaConsumer",
            return_value=mock_kafka_consumer,
        ):
            # Start and immediately stop
            await consumer.start()
            await consumer.stop()

        mock_kafka_consumer.start.assert_called_once()
        assert consumer._running is False  # After stop

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, consumer: EventConsumer) -> None:
        """Test start when already running does nothing."""
        consumer._running = True

        # Should return early without creating a new consumer
        await consumer.start()
        assert consumer._consumer is None  # No consumer created

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self, consumer: EventConsumer) -> None:
        """Test stop cleans up resources."""
        mock_consumer = AsyncMock()
        consumer._consumer = mock_consumer
        consumer._running = True
        consumer._consume_task = asyncio.create_task(asyncio.sleep(10))

        await consumer.stop()

        assert consumer._running is False
        assert consumer._consumer is None
        assert consumer._consume_task is None
        mock_consumer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, consumer: EventConsumer) -> None:
        """Test stop when not running does nothing."""
        await consumer.stop()  # Should not raise


class TestEventConsumerIntegration:
    """Integration-style tests for EventConsumer."""

    @pytest.mark.asyncio
    async def test_multiple_handlers(self) -> None:
        """Test multiple handlers can be registered."""
        consumer = EventConsumer(
            group_id="test",
            topics=["test-topic"],
        )

        handler1 = AsyncMock()
        handler2 = AsyncMock()

        consumer.register_handler("type1", handler1, min_priority=0)
        consumer.register_handler("type2", handler2, min_priority=1)

        # Handle type1 event
        await consumer._handle_message(
            {
                "event_type": "type1",
                "event_id": "1",
                "priority": 0,
            }
        )
        handler1.assert_called_once()
        handler2.assert_not_called()

        # Handle type2 event
        await consumer._handle_message(
            {
                "event_type": "type2",
                "event_id": "2",
                "priority": 2,
            }
        )
        handler2.assert_called_once()
