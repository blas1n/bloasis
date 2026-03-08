"""Broker adapter interface — abstract base for multi-broker support.

Defines the contract that all broker integrations must implement.
This is a pure interface with no I/O — implementations live in app/services/brokers/.
"""

from abc import ABC, abstractmethod
from decimal import Decimal

from .models import BrokerAccountInfo, BrokerPosition, OrderResult


class BrokerAdapter(ABC):
    """Abstract broker adapter defining the interface for order execution.

    All broker-specific code (Alpaca, Mock, future brokers) must implement
    this interface. The adapter is the sole communication channel with the broker.
    """

    @property
    @abstractmethod
    def broker_type(self) -> str:
        """Return the broker type identifier (e.g. 'alpaca', 'mock')."""

    @abstractmethod
    async def get_account(self) -> BrokerAccountInfo:
        """Get current account information (equity, cash, buying power)."""

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        """Get all open positions from the broker."""

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        order_type: str,
        client_order_id: str,
    ) -> OrderResult:
        """Submit an order to the broker.

        Args:
            symbol: Ticker symbol.
            side: "buy" or "sell".
            qty: Order quantity.
            price: Limit price (ignored for market orders).
            order_type: "market" or "limit".
            client_order_id: Idempotency key to prevent duplicate orders.

        Returns:
            OrderResult with broker-assigned order_id and initial status.
        """

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Poll the broker for current order status.

        Used by the background order processor to track submitted/partially_filled orders.
        """

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an order on the broker (Saga compensation).

        Returns:
            True if cancellation was successful or order was already cancelled.
        """

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test broker connectivity and credential validity."""
