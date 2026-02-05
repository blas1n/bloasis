"""Tests for Event Publisher."""

from unittest.mock import AsyncMock, patch

import pytest

from src.utils.event_publisher import EventPublisher


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

        # Should not create new producer
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

        # Should not raise
        await publisher.close()

    @pytest.mark.asyncio
    async def test_publish_risk_decision(self):
        """Test publishing risk decision event."""
        mock_producer = AsyncMock()

        publisher = EventPublisher(producer=mock_producer)

        await publisher.publish_risk_decision(
            user_id="test-user",
            symbol="AAPL",
            action="buy",
            approved=True,
            risk_score=0.3,
            reasoning="Approved by consensus",
        )

        mock_producer.send_and_wait.assert_called_once()
        call_args = mock_producer.send_and_wait.call_args

        assert call_args[0][0] == "risk-decisions"
        assert call_args[1]["key"] == b"test-user"

        event = call_args[1]["value"]
        assert event["event_type"] == "risk_decision"
        assert event["user_id"] == "test-user"
        assert event["symbol"] == "AAPL"
        assert event["approved"] is True

    @pytest.mark.asyncio
    async def test_publish_risk_decision_not_connected(self):
        """Test publishing when not connected."""
        publisher = EventPublisher()

        # Should log warning but not raise
        with patch("src.utils.event_publisher.logger") as mock_logger:
            await publisher.publish_risk_decision(
                user_id="test-user",
                symbol="AAPL",
                action="buy",
                approved=True,
                risk_score=0.3,
                reasoning="OK",
            )

            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_risk_decision_error(self):
        """Test publishing with error."""
        mock_producer = AsyncMock()
        mock_producer.send_and_wait.side_effect = Exception("Connection error")

        publisher = EventPublisher(producer=mock_producer)

        with pytest.raises(Exception):
            await publisher.publish_risk_decision(
                user_id="test-user",
                symbol="AAPL",
                action="buy",
                approved=True,
                risk_score=0.3,
                reasoning="OK",
            )

    @pytest.mark.asyncio
    async def test_publish_event(self):
        """Test publishing generic event."""
        mock_producer = AsyncMock()

        publisher = EventPublisher(producer=mock_producer)

        event = {"type": "test", "data": "value"}
        await publisher.publish_event("test-topic", event)

        mock_producer.send_and_wait.assert_called_once_with("test-topic", value=event)

    @pytest.mark.asyncio
    async def test_publish_event_not_connected(self):
        """Test publishing event when not connected."""
        publisher = EventPublisher()

        with patch("src.utils.event_publisher.logger") as mock_logger:
            await publisher.publish_event("test-topic", {"data": "value"})

            mock_logger.warning.assert_called_once()
