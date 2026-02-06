"""Tests for message models."""

from src.models import (
    ExecutionEventData,
    MarketAlertData,
    MessageType,
    RegimeChangeData,
    RiskAlertData,
    WebSocketMessage,
)


class TestMessageType:
    """Test cases for MessageType enum."""

    def test_message_types(self) -> None:
        """Test all message type values."""
        assert MessageType.REGIME_CHANGE.value == "regime_change"
        assert MessageType.MARKET_ALERT.value == "market_alert"
        assert MessageType.RISK_ALERT.value == "risk_alert"
        assert MessageType.ORDER_EXECUTED.value == "order_executed"

    def test_message_type_is_string(self) -> None:
        """Test that message types are strings."""
        assert isinstance(MessageType.REGIME_CHANGE.value, str)
        assert isinstance(MessageType.MARKET_ALERT.value, str)


class TestWebSocketMessage:
    """Test cases for WebSocketMessage model."""

    def test_create_message(self) -> None:
        """Test creating a WebSocket message."""
        message = WebSocketMessage(
            type=MessageType.REGIME_CHANGE,
            data={"new_regime": "bull", "confidence": 0.85},
        )

        assert message.type == MessageType.REGIME_CHANGE
        assert message.data["new_regime"] == "bull"
        assert message.data["confidence"] == 0.85

    def test_message_serialization(self) -> None:
        """Test message serialization."""
        message = WebSocketMessage(
            type=MessageType.MARKET_ALERT,
            data={"alert_type": "volatility_spike"},
        )

        data = message.model_dump()
        assert data["type"] == "market_alert"
        assert data["data"]["alert_type"] == "volatility_spike"


class TestRegimeChangeData:
    """Test cases for RegimeChangeData model."""

    def test_create_regime_change(self) -> None:
        """Test creating regime change data."""
        data = RegimeChangeData(
            new_regime="bull",
            previous_regime="sideways",
            confidence=0.85,
            timestamp="2025-01-29T10:00:00Z",
        )

        assert data.new_regime == "bull"
        assert data.previous_regime == "sideways"
        assert data.confidence == 0.85
        assert data.timestamp == "2025-01-29T10:00:00Z"

    def test_optional_previous_regime(self) -> None:
        """Test that previous_regime is optional."""
        data = RegimeChangeData(
            new_regime="bull",
            confidence=0.85,
            timestamp="2025-01-29T10:00:00Z",
        )

        assert data.new_regime == "bull"
        assert data.previous_regime is None


class TestMarketAlertData:
    """Test cases for MarketAlertData model."""

    def test_create_market_alert(self) -> None:
        """Test creating market alert data."""
        data = MarketAlertData(
            alert_type="volatility_spike",
            severity="high",
            message="VIX exceeded 30",
            timestamp="2025-01-29T10:05:00Z",
        )

        assert data.alert_type == "volatility_spike"
        assert data.severity == "high"
        assert data.message == "VIX exceeded 30"
        assert data.timestamp == "2025-01-29T10:05:00Z"


class TestRiskAlertData:
    """Test cases for RiskAlertData model."""

    def test_create_risk_alert(self) -> None:
        """Test creating risk alert data."""
        data = RiskAlertData(
            user_id="user-123",
            alert_type="position_limit",
            severity="medium",
            message="Position size exceeds 10% of portfolio",
            portfolio_id="portfolio-456",
            timestamp="2025-01-29T10:10:00Z",
        )

        assert data.user_id == "user-123"
        assert data.alert_type == "position_limit"
        assert data.severity == "medium"
        assert data.message == "Position size exceeds 10% of portfolio"
        assert data.portfolio_id == "portfolio-456"
        assert data.timestamp == "2025-01-29T10:10:00Z"

    def test_optional_portfolio_id(self) -> None:
        """Test that portfolio_id is optional."""
        data = RiskAlertData(
            user_id="user-123",
            alert_type="position_limit",
            severity="medium",
            message="Test alert",
            timestamp="2025-01-29T10:10:00Z",
        )

        assert data.portfolio_id is None


class TestExecutionEventData:
    """Test cases for ExecutionEventData model."""

    def test_create_execution_event(self) -> None:
        """Test creating execution event data."""
        data = ExecutionEventData(
            user_id="user-123",
            order_id="order-789",
            symbol="AAPL",
            side="buy",
            qty="10",
            filled_qty="10",
            filled_avg_price="175.50",
            status="filled",
            timestamp="2025-01-29T10:15:00Z",
        )

        assert data.user_id == "user-123"
        assert data.order_id == "order-789"
        assert data.symbol == "AAPL"
        assert data.side == "buy"
        assert data.qty == "10"
        assert data.filled_qty == "10"
        assert data.filled_avg_price == "175.50"
        assert data.status == "filled"
        assert data.timestamp == "2025-01-29T10:15:00Z"

    def test_optional_filled_avg_price(self) -> None:
        """Test that filled_avg_price is optional."""
        data = ExecutionEventData(
            user_id="user-123",
            order_id="order-789",
            symbol="AAPL",
            side="buy",
            qty="10",
            filled_qty="0",
            status="submitted",
            timestamp="2025-01-29T10:15:00Z",
        )

        assert data.filled_avg_price is None
