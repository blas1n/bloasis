"""Test fixtures for Notification Service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.websocket_manager import WebSocketManager


@pytest.fixture
def ws_manager() -> WebSocketManager:
    """Create a fresh WebSocketManager instance."""
    return WebSocketManager()


@pytest.fixture
def mock_websocket() -> MagicMock:
    """Create a mock WebSocket connection."""
    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.send_json = AsyncMock()
    websocket.receive_text = AsyncMock(return_value='{"type": "ping"}')
    websocket.close = AsyncMock()
    return websocket


@pytest.fixture
def mock_websocket_factory() -> callable:
    """Factory to create multiple mock WebSocket connections."""

    def _create_mock_websocket() -> MagicMock:
        websocket = MagicMock()
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock()
        websocket.receive_text = AsyncMock(return_value='{"type": "ping"}')
        websocket.close = AsyncMock()
        return websocket

    return _create_mock_websocket


@pytest.fixture
def mock_event_consumer() -> MagicMock:
    """Create a mock EventConsumer."""
    consumer = MagicMock()
    consumer.start = AsyncMock()
    consumer.stop = AsyncMock()
    consumer.register_handler = MagicMock()
    consumer.is_running = True
    return consumer


@pytest.fixture
def sample_regime_change_event() -> dict:
    """Sample regime change event."""
    return {
        "event_type": "regime_change",
        "event_id": "evt-123",
        "priority": 2,
        "new_regime": "bull",
        "previous_regime": "sideways",
        "confidence": 0.85,
        "timestamp": "2025-01-29T10:00:00Z",
    }


@pytest.fixture
def sample_market_alert_event() -> dict:
    """Sample market alert event."""
    return {
        "event_type": "market_alert",
        "event_id": "evt-124",
        "priority": 3,
        "alert_type": "volatility_spike",
        "severity": "high",
        "message": "VIX exceeded 30",
        "timestamp": "2025-01-29T10:05:00Z",
    }


@pytest.fixture
def sample_risk_alert_event() -> dict:
    """Sample risk alert event."""
    return {
        "event_type": "risk_alert",
        "event_id": "evt-125",
        "priority": 2,
        "user_id": "user-123",
        "alert_type": "position_limit",
        "severity": "medium",
        "message": "Position size exceeds 10% of portfolio",
        "portfolio_id": "portfolio-456",
        "timestamp": "2025-01-29T10:10:00Z",
    }


@pytest.fixture
def sample_execution_event() -> dict:
    """Sample execution event."""
    return {
        "event_type": "order_executed",
        "event_id": "evt-126",
        "priority": 1,
        "user_id": "user-123",
        "order_id": "order-789",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "filled_qty": "10",
        "filled_avg_price": "175.50",
        "status": "filled",
        "timestamp": "2025-01-29T10:15:00Z",
    }


@pytest.fixture
def sample_execution_event_no_user() -> dict:
    """Sample execution event without user_id."""
    return {
        "event_type": "order_executed",
        "event_id": "evt-127",
        "priority": 1,
        "order_id": "order-790",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "status": "filled",
        "timestamp": "2025-01-29T10:20:00Z",
    }
