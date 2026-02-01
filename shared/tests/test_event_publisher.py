"""
Unit tests for EventPublisher.
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from shared.utils import EventPriority, EventPublisher


class TestEventPriority:
    """Tests for EventPriority enum."""

    def test_priority_values(self) -> None:
        """Test priority values match events.proto."""
        assert EventPriority.UNSPECIFIED == 0
        assert EventPriority.LOW == 1
        assert EventPriority.MEDIUM == 2
        assert EventPriority.HIGH == 3
        assert EventPriority.CRITICAL == 4

    def test_priority_ordering(self) -> None:
        """Test priorities can be compared."""
        assert EventPriority.UNSPECIFIED < EventPriority.LOW
        assert EventPriority.LOW < EventPriority.MEDIUM
        assert EventPriority.MEDIUM < EventPriority.HIGH
        assert EventPriority.HIGH < EventPriority.CRITICAL


class TestEventPublisher:
    """Tests for EventPublisher class."""

    @pytest.fixture
    def mock_redpanda(self) -> AsyncMock:
        """Create a mock RedpandaClient."""
        return AsyncMock()

    @pytest.fixture
    def publisher(self, mock_redpanda: AsyncMock) -> EventPublisher:
        """Create an EventPublisher with mocked Redpanda."""
        return EventPublisher(mock_redpanda)

    @pytest.mark.asyncio
    async def test_publish_regime_change(
        self, publisher: EventPublisher, mock_redpanda: AsyncMock
    ) -> None:
        """Test publishing regime change event."""
        event_id = await publisher.publish_regime_change(
            previous_regime="bull",
            new_regime="bear",
            confidence=0.85,
            reasoning="VIX spike detected",
        )

        # Verify event ID is returned
        assert event_id is not None
        assert len(event_id) == 36  # UUID format

        # Verify Redpanda was called
        mock_redpanda.publish.assert_called_once()
        call_args = mock_redpanda.publish.call_args

        # Check topic
        assert call_args.kwargs["topic"] == "regime-events"

        # Check message content
        message = call_args.kwargs["message"]
        assert message["event_type"] == "regime_change"
        assert message["previous_regime"] == "bull"
        assert message["new_regime"] == "bear"
        assert message["confidence"] == 0.85
        assert message["reasoning"] == "VIX spike detected"
        assert message["priority"] == EventPriority.HIGH.value

        # Check partition key (HIGH = 3)
        assert call_args.kwargs["partition_key"] == "priority-3"

    @pytest.mark.asyncio
    async def test_publish_regime_change_with_metadata(
        self, publisher: EventPublisher, mock_redpanda: AsyncMock
    ) -> None:
        """Test publishing regime change with metadata."""
        await publisher.publish_regime_change(
            previous_regime="sideways",
            new_regime="crisis",
            confidence=0.95,
            reasoning="Market crash",
            priority=EventPriority.CRITICAL,
            metadata={"source": "emergency", "alert_id": "123"},
        )

        message = mock_redpanda.publish.call_args.kwargs["message"]
        assert message["priority"] == EventPriority.CRITICAL.value
        assert message["metadata"]["source"] == "emergency"
        assert message["metadata"]["alert_id"] == "123"

    @pytest.mark.asyncio
    async def test_publish_market_alert(
        self, publisher: EventPublisher, mock_redpanda: AsyncMock
    ) -> None:
        """Test publishing market alert event."""
        event_id = await publisher.publish_market_alert(
            alert_type="vix_spike",
            severity="warning",
            message="VIX exceeded 30",
            indicators={"vix": "32.5"},
        )

        assert event_id is not None
        mock_redpanda.publish.assert_called_once()

        call_args = mock_redpanda.publish.call_args
        assert call_args.kwargs["topic"] == "alert-events"

        message = call_args.kwargs["message"]
        assert message["event_type"] == "market_alert"
        assert message["alert_type"] == "vix_spike"
        assert message["severity"] == "warning"
        assert message["message"] == "VIX exceeded 30"
        assert message["indicators"]["vix"] == "32.5"

    @pytest.mark.asyncio
    async def test_publish_market_alert_critical_priority(
        self, publisher: EventPublisher, mock_redpanda: AsyncMock
    ) -> None:
        """Test publishing critical market alert."""
        await publisher.publish_market_alert(
            alert_type="flash_crash",
            severity="critical",
            message="Market crashed 10%",
            priority=EventPriority.CRITICAL,
        )

        message = mock_redpanda.publish.call_args.kwargs["message"]
        assert message["priority"] == EventPriority.CRITICAL.value
        assert mock_redpanda.publish.call_args.kwargs["partition_key"] == "priority-4"

    @pytest.mark.asyncio
    async def test_publish_strategy_signal(
        self, publisher: EventPublisher, mock_redpanda: AsyncMock
    ) -> None:
        """Test publishing strategy signal event."""
        event_id = await publisher.publish_strategy_signal(
            strategy_id="momentum-v1",
            signal_type="entry",
            symbol="AAPL",
            action="buy",
            confidence=0.80,
            parameters={"target_price": "150.00"},
        )

        assert event_id is not None
        call_args = mock_redpanda.publish.call_args
        assert call_args.kwargs["topic"] == "strategy-events"

        message = call_args.kwargs["message"]
        assert message["event_type"] == "strategy_signal"
        assert message["strategy_id"] == "momentum-v1"
        assert message["signal_type"] == "entry"
        assert message["symbol"] == "AAPL"
        assert message["action"] == "buy"
        assert message["confidence"] == 0.80
        assert message["parameters"]["target_price"] == "150.00"

    @pytest.mark.asyncio
    async def test_publish_risk_alert(
        self, publisher: EventPublisher, mock_redpanda: AsyncMock
    ) -> None:
        """Test publishing risk alert event."""
        event_id = await publisher.publish_risk_alert(
            risk_type="drawdown",
            severity="warning",
            message="Portfolio drawdown exceeded 10%",
            affected_portfolio="portfolio-123",
            metrics={"current_drawdown": "12.5%"},
        )

        assert event_id is not None
        call_args = mock_redpanda.publish.call_args
        assert call_args.kwargs["topic"] == "risk-events"

        message = call_args.kwargs["message"]
        assert message["event_type"] == "risk_alert"
        assert message["risk_type"] == "drawdown"
        assert message["severity"] == "warning"
        assert message["affected_portfolio"] == "portfolio-123"
        assert message["metrics"]["current_drawdown"] == "12.5%"

    @pytest.mark.asyncio
    async def test_event_timestamp_format(
        self, publisher: EventPublisher, mock_redpanda: AsyncMock
    ) -> None:
        """Test event timestamp is ISO 8601 format."""
        await publisher.publish_regime_change(
            previous_regime="bull",
            new_regime="bear",
            confidence=0.75,
            reasoning="Test",
        )

        message = mock_redpanda.publish.call_args.kwargs["message"]
        timestamp = message["timestamp"]

        # Verify it's a valid ISO 8601 timestamp
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed is not None
        assert parsed.tzinfo is not None  # Has timezone info

    @pytest.mark.asyncio
    async def test_topic_mapping(self, publisher: EventPublisher) -> None:
        """Test topic mapping is correct."""
        assert EventPublisher.TOPIC_MAPPING["regime_change"] == "regime-events"
        assert EventPublisher.TOPIC_MAPPING["market_alert"] == "alert-events"
        assert EventPublisher.TOPIC_MAPPING["strategy_signal"] == "strategy-events"
        assert EventPublisher.TOPIC_MAPPING["risk_alert"] == "risk-events"
