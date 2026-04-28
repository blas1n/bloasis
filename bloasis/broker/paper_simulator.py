"""Offline paper broker for tests + `bloasis trade dry-run`.

Simulates fills at the user-supplied price (typically last close + bps
slippage). Tracks cash / positions in memory. No network calls — used
when the user wants to see what `trade live` *would* do without setting
up an Alpaca account.

Idempotency: `place_market_order` reuses the result for an already-seen
`client_order_id`, mirroring real broker behavior.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from bloasis.broker.protocols import (
    AccountInfo,
    BrokerOrder,
    BrokerPosition,
    OrderResult,
)

PriceFn = Callable[[str], float]


@dataclass
class _SimPosition:
    quantity: float
    avg_cost: float
    last_price: float


@dataclass
class InMemoryPaperBroker:
    """Tiny paper broker. `price_fn` returns fill price for each symbol."""

    price_fn: PriceFn
    initial_cash: float = 100_000.0
    slippage_bps: float = 0.0
    cash: float = field(init=False)
    positions: dict[str, _SimPosition] = field(init=False, default_factory=dict)
    submitted: dict[str, OrderResult] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    @property
    def mode(self) -> Literal["paper", "live", "offline"]:
        return "offline"

    # ------------------------------------------------------------------

    def get_account(self) -> AccountInfo:
        equity = self.cash + sum(p.quantity * p.last_price for p in self.positions.values())
        return AccountInfo(
            cash=self.cash,
            equity=equity,
            buying_power=self.cash,
        )

    def get_positions(self) -> list[BrokerPosition]:
        out: list[BrokerPosition] = []
        for sym, pos in self.positions.items():
            out.append(
                BrokerPosition(
                    symbol=sym,
                    quantity=pos.quantity,
                    avg_cost=pos.avg_cost,
                    current_price=pos.last_price,
                    market_value=pos.quantity * pos.last_price,
                )
            )
        return out

    def place_market_order(self, order: BrokerOrder) -> OrderResult:
        # Idempotency: same client_order_id -> same result.
        if order.client_order_id in self.submitted:
            return self.submitted[order.client_order_id]

        try:
            ref_price = self.price_fn(order.symbol)
        except KeyError as exc:
            return self._reject(order, reason=f"unknown symbol: {exc}")
        if ref_price <= 0:
            return self._reject(order, reason="non-positive reference price")

        slippage = ref_price * self.slippage_bps / 10_000
        fill_price = ref_price + slippage if order.side == "buy" else ref_price - slippage

        if order.side == "buy":
            cost = fill_price * order.qty
            if cost > self.cash + 1e-6:
                return self._reject(order, reason="insufficient cash")
            self.cash -= cost
            existing = self.positions.get(order.symbol)
            if existing is None:
                self.positions[order.symbol] = _SimPosition(
                    quantity=order.qty,
                    avg_cost=fill_price,
                    last_price=fill_price,
                )
            else:
                total_qty = existing.quantity + order.qty
                existing.avg_cost = (
                    existing.avg_cost * existing.quantity + fill_price * order.qty
                ) / total_qty
                existing.quantity = total_qty
                existing.last_price = fill_price
        else:  # sell
            existing = self.positions.get(order.symbol)
            if existing is None or existing.quantity < order.qty - 1e-9:
                return self._reject(
                    order,
                    reason=f"position too small to sell {order.qty}",
                )
            self.cash += fill_price * order.qty
            existing.quantity -= order.qty
            existing.last_price = fill_price
            if existing.quantity <= 1e-9:
                del self.positions[order.symbol]

        result = OrderResult(
            order_id=str(uuid.uuid4()),
            client_order_id=order.client_order_id,
            status="filled",
            filled_qty=order.qty,
            filled_avg_price=fill_price,
            submitted_at=datetime.now(tz=UTC),
        )
        self.submitted[order.client_order_id] = result
        return result

    def cancel_order(self, order_id: str) -> bool:
        # All paper orders fill instantly; nothing to cancel.
        return False

    # ------------------------------------------------------------------

    def _reject(self, order: BrokerOrder, *, reason: str) -> OrderResult:
        result = OrderResult(
            order_id=str(uuid.uuid4()),
            client_order_id=order.client_order_id,
            status="rejected",
            filled_qty=0.0,
            filled_avg_price=0.0,
            submitted_at=datetime.now(tz=UTC),
            reason=reason,
        )
        self.submitted[order.client_order_id] = result
        return result
