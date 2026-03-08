"""Mock broker adapter — for development and testing without a live broker.

Simulates order execution with immediate fills at requested price.
"""

import logging
import uuid
from decimal import Decimal

from ...core.broker import BrokerAdapter
from ...core.models import BrokerAccountInfo, BrokerPosition, OrderResult, OrderSide, OrderStatus

logger = logging.getLogger(__name__)


class MockBrokerAdapter(BrokerAdapter):
    """Mock broker that simulates immediate fills.

    All orders are filled at the requested price. Positions are tracked
    in-memory for the lifetime of this adapter instance.
    """

    def __init__(self) -> None:
        self._positions: dict[str, BrokerPosition] = {}
        self._cash = Decimal("100000")
        self._orders: dict[str, OrderResult] = {}

    @property
    def broker_type(self) -> str:
        return "mock"

    async def get_account(self) -> BrokerAccountInfo:
        invested = sum((p.market_value for p in self._positions.values()), Decimal("0"))
        equity = self._cash + invested
        return BrokerAccountInfo(
            equity=equity,
            cash=self._cash,
            buying_power=self._cash,
        )

    async def get_positions(self) -> list[BrokerPosition]:
        return [p for p in self._positions.values() if p.quantity > 0]

    async def submit_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        order_type: str,
        client_order_id: str,
    ) -> OrderResult:
        order_id = str(uuid.uuid4())
        logger.info(
            "Mock order filled",
            extra={"symbol": symbol, "side": side, "qty": str(qty)},
        )

        # Update in-memory positions and cash
        order_side = OrderSide(side)
        if order_side == OrderSide.BUY:
            self._cash -= qty * price
            existing = self._positions.get(symbol)
            if existing:
                new_qty = existing.quantity + qty
                new_avg = ((existing.avg_entry_price * existing.quantity) + (price * qty)) / new_qty
                self._positions[symbol] = BrokerPosition(
                    symbol=symbol,
                    quantity=new_qty,
                    avg_entry_price=new_avg.quantize(Decimal("0.01")),
                    current_price=price,
                    market_value=new_qty * price,
                )
            else:
                self._positions[symbol] = BrokerPosition(
                    symbol=symbol,
                    quantity=qty,
                    avg_entry_price=price,
                    current_price=price,
                    market_value=qty * price,
                )
        else:
            self._cash += qty * price
            existing = self._positions.get(symbol)
            if existing:
                remaining = existing.quantity - qty
                if remaining <= 0:
                    del self._positions[symbol]
                else:
                    self._positions[symbol] = BrokerPosition(
                        symbol=symbol,
                        quantity=remaining,
                        avg_entry_price=existing.avg_entry_price,
                        current_price=price,
                        market_value=remaining * price,
                    )

        result = OrderResult(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=order_side,
            qty=qty,
            status=OrderStatus.FILLED,
            filled_qty=qty,
            filled_avg_price=price,
        )
        self._orders[order_id] = result
        return result

    async def get_order_status(self, broker_order_id: str) -> OrderResult:
        if broker_order_id in self._orders:
            return self._orders[broker_order_id]
        return OrderResult(
            order_id=broker_order_id,
            symbol="",
            side=OrderSide.BUY,
            qty=Decimal("0"),
            status=OrderStatus.CANCELLED,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        if broker_order_id in self._orders:
            self._orders[broker_order_id].status = OrderStatus.CANCELLED
        return True

    async def test_connection(self) -> bool:
        return True
