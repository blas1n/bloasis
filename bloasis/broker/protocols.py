"""Provider-agnostic broker Protocol + plain-data record types.

Each concrete broker (InMemory, Alpaca, future Interactive Brokers)
implements this Protocol. Trade pipeline code never imports a specific
broker SDK; it takes a `BrokerAdapter` and lets dependency injection
decide paper vs live vs offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

OrderSide = Literal["buy", "sell"]
OrderStatus = Literal["accepted", "filled", "partially_filled", "rejected", "canceled"]


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    """Order request handed to a broker. `qty` is shares (fractional OK)."""

    symbol: str
    side: OrderSide
    qty: float
    client_order_id: str  # idempotency key — broker rejects dup if already submitted


@dataclass(frozen=True, slots=True)
class OrderResult:
    """Broker's response to a `place_market_order` call."""

    order_id: str
    client_order_id: str
    status: OrderStatus
    filled_qty: float
    filled_avg_price: float
    submitted_at: datetime
    reason: str = ""  # populated for rejections


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    """Snapshot of a held position from the broker side."""

    symbol: str
    quantity: float
    avg_cost: float
    current_price: float
    market_value: float


@dataclass(frozen=True, slots=True)
class AccountInfo:
    """Top-level account snapshot (cash + total equity)."""

    cash: float
    equity: float
    buying_power: float
    currency: str = "USD"


@runtime_checkable
class BrokerAdapter(Protocol):
    """Minimum surface area every broker must support.

    All methods are synchronous in v1. Async wrappers can be added later
    for batched live orders without breaking the contract.
    """

    @property
    def mode(self) -> Literal["paper", "live", "offline"]: ...

    def get_account(self) -> AccountInfo: ...

    def get_positions(self) -> list[BrokerPosition]: ...

    def place_market_order(self, order: BrokerOrder) -> OrderResult: ...

    def cancel_order(self, order_id: str) -> bool:
        """Best-effort cancel. Returns True if accepted by the broker."""
        ...
