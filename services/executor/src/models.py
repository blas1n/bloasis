"""Data models for Executor Service."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OrderStatus(str, Enum):
    """Order status values."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderSide(str, Enum):
    """Order side (buy/sell)."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order types."""

    MARKET = "market"
    LIMIT = "limit"
    BRACKET = "bracket"


@dataclass
class OrderResult:
    """Order execution result."""

    order_id: str
    client_order_id: str
    symbol: str
    side: str
    qty: Decimal
    status: OrderStatus
    filled_qty: Decimal
    filled_avg_price: Decimal | None
    submitted_at: str
    filled_at: str | None
    error_message: str | None = None


@dataclass
class AccountInfo:
    """Account information from Alpaca."""

    cash: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    equity: Decimal
