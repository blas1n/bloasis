"""Message models for Notification Service."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class MessageType(str, Enum):
    """WebSocket message types."""

    REGIME_CHANGE = "regime_change"
    MARKET_ALERT = "market_alert"
    RISK_ALERT = "risk_alert"
    ORDER_EXECUTED = "order_executed"


class WebSocketMessage(BaseModel):
    """WebSocket message format.

    Attributes:
        type: Message type identifier.
        data: Message payload.
    """

    type: MessageType
    data: dict[str, Any]


class RegimeChangeData(BaseModel):
    """Regime change event data.

    Attributes:
        new_regime: The new market regime.
        previous_regime: The previous market regime.
        confidence: Confidence score (0.0 - 1.0).
        timestamp: ISO 8601 timestamp.
    """

    new_regime: str
    previous_regime: str | None = None
    confidence: float
    timestamp: str


class MarketAlertData(BaseModel):
    """Market alert event data.

    Attributes:
        alert_type: Type of alert (e.g., "volatility_spike").
        severity: Alert severity level.
        message: Human-readable alert message.
        timestamp: ISO 8601 timestamp.
    """

    alert_type: str
    severity: str
    message: str
    timestamp: str


class RiskAlertData(BaseModel):
    """Risk alert event data.

    Attributes:
        user_id: Target user ID.
        alert_type: Type of risk alert.
        severity: Alert severity level.
        message: Human-readable alert message.
        portfolio_id: Related portfolio ID.
        timestamp: ISO 8601 timestamp.
    """

    user_id: str
    alert_type: str
    severity: str
    message: str
    portfolio_id: str | None = None
    timestamp: str


class ExecutionEventData(BaseModel):
    """Execution event data.

    Attributes:
        user_id: Target user ID.
        order_id: Order identifier.
        symbol: Trading symbol.
        side: Order side (buy/sell).
        qty: Quantity.
        filled_qty: Filled quantity.
        filled_avg_price: Average fill price.
        status: Order status.
        timestamp: ISO 8601 timestamp.
    """

    user_id: str
    order_id: str
    symbol: str
    side: str
    qty: str
    filled_qty: str
    filled_avg_price: str | None = None
    status: str
    timestamp: str
