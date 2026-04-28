"""SimulatedPortfolio — in-memory cash + positions for backtests.

Tracks cash, average cost, and current price per symbol. `mark()` updates
position values from the latest bar so `total_equity()` is always current.

SL/TP enforcement happens here too: `check_stops()` returns implicit SELL
fills when a held bar's high/low touches the stored stop or take-profit
levels. This mirrors what a broker would do for resting OCO orders.

All state is in-memory; the engine persists to `equity_curve` and `trades`
tables via `bloasis/storage/writers.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass


@dataclass(slots=True)
class Position:
    symbol: str
    quantity: float
    avg_cost: float
    sector: str | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    last_price: float = 0.0
    opened_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    """Concrete trade execution record (the engine persists these as `trades`)."""

    timestamp: datetime
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    fees: float = 0.0
    slippage_bps: float = 0.0
    sector: str | None = None
    realized_pnl: float | None = None
    reason: str = ""


@dataclass(slots=True)
class SimulatedPortfolio:
    """Long-only simulated portfolio."""

    initial_capital: float
    cash: float = field(init=False)
    positions: dict[str, Position] = field(init=False)
    trade_count: int = field(init=False, default=0)
    realized_pnl_total: float = field(init=False, default=0.0)
    win_count: int = field(init=False, default=0)
    loss_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.cash = float(self.initial_capital)
        self.positions = {}

    # ------------------------------------------------------------------
    # state queries
    # ------------------------------------------------------------------

    def held_symbols(self) -> set[str]:
        return set(self.positions.keys())

    def invested_value(self) -> float:
        return sum(p.quantity * p.last_price for p in self.positions.values())

    def total_equity(self) -> float:
        return self.cash + self.invested_value()

    def sector_concentrations(self) -> dict[str, float]:
        equity = self.total_equity()
        if equity <= 0:
            return {}
        out: dict[str, float] = {}
        for p in self.positions.values():
            sector = p.sector or "_unknown"
            out[sector] = out.get(sector, 0.0) + (p.quantity * p.last_price) / equity
        return out

    # ------------------------------------------------------------------
    # mutation: apply fills, mark to market, check stops
    # ------------------------------------------------------------------

    def apply(self, fill: Fill) -> Fill:
        """Apply a fill to cash + positions; return the (possibly enriched) fill.

        For BUY: deducts cost from cash, adds to position with weighted-avg cost.
        For SELL: closes (full or partial) position, computes realized PnL,
        credits cash. Sets `realized_pnl` on the returned Fill copy.
        """
        notional = fill.quantity * fill.price
        if fill.side == "buy":
            cost = notional + fill.fees
            if cost > self.cash + 1e-6:
                # Allow rounding slack; otherwise refuse to over-spend cash.
                raise ValueError(f"insufficient cash: need {cost:.2f}, have {self.cash:.2f}")
            self.cash -= cost
            existing = self.positions.get(fill.symbol)
            if existing is None:
                self.positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    quantity=fill.quantity,
                    avg_cost=fill.price,
                    sector=fill.sector,
                    last_price=fill.price,
                    opened_at=fill.timestamp,
                )
            else:
                # Weighted average cost on add.
                total_qty = existing.quantity + fill.quantity
                existing.avg_cost = (
                    existing.avg_cost * existing.quantity + fill.price * fill.quantity
                ) / total_qty
                existing.quantity = total_qty
                existing.last_price = fill.price
            self.trade_count += 1
            return fill

        # SELL
        existing = self.positions.get(fill.symbol)
        if existing is None or existing.quantity < fill.quantity - 1e-9:
            raise ValueError(
                f"cannot sell {fill.quantity} of {fill.symbol}: "
                f"position={0 if existing is None else existing.quantity}"
            )
        proceeds = notional - fill.fees
        realized = (fill.price - existing.avg_cost) * fill.quantity - fill.fees
        self.cash += proceeds
        self.realized_pnl_total += realized
        if realized > 0:
            self.win_count += 1
        elif realized < 0:
            self.loss_count += 1
        existing.quantity -= fill.quantity
        existing.last_price = fill.price
        if existing.quantity <= 1e-9:
            del self.positions[fill.symbol]
        self.trade_count += 1

        return Fill(
            timestamp=fill.timestamp,
            symbol=fill.symbol,
            side=fill.side,
            quantity=fill.quantity,
            price=fill.price,
            fees=fill.fees,
            slippage_bps=fill.slippage_bps,
            sector=fill.sector,
            realized_pnl=realized,
            reason=fill.reason,
        )

    def mark(self, prices: Mapping[str, float]) -> None:
        """Update last_price for each position from latest close prices."""
        for sym, pos in self.positions.items():
            if sym in prices:
                pos.last_price = float(prices[sym])

    def attach_levels(
        self,
        symbol: str,
        *,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> None:
        """Attach SL/TP levels to a held position so `check_stops` can act."""
        if symbol in self.positions:
            self.positions[symbol].stop_loss = stop_loss
            self.positions[symbol].take_profit = take_profit

    def check_stops(
        self,
        bars_today: Mapping[str, dict[str, float]],
        timestamp: datetime,
        slippage_bps: float = 0.0,
    ) -> list[Fill]:
        """Emit SELL fills for any position whose levels are touched today.

        `bars_today` maps symbol to {'high': ..., 'low': ..., 'close': ...}.
        Stop-loss is hit when low <= stop_loss; take-profit when high >=
        take_profit. SL precedence over TP if both are touched on the same
        bar (conservative: assume worst).
        """
        out: list[Fill] = []
        for sym in list(self.positions.keys()):
            pos = self.positions[sym]
            bar = bars_today.get(sym)
            if bar is None:
                continue
            high = float(bar["high"])
            low = float(bar["low"])
            sl = pos.stop_loss
            tp = pos.take_profit
            fill_price: float | None = None
            reason = ""
            if sl is not None and low <= sl:
                fill_price = sl
                reason = "stop-loss hit"
            elif tp is not None and high >= tp:
                fill_price = tp
                reason = "take-profit hit"
            if fill_price is None:
                continue
            slippage = fill_price * slippage_bps / 10_000
            executed_price = fill_price - slippage  # SELL — we receive less
            fill = Fill(
                timestamp=timestamp,
                symbol=sym,
                side="sell",
                quantity=pos.quantity,
                price=executed_price,
                fees=0.0,
                slippage_bps=slippage_bps,
                sector=pos.sector,
                reason=reason,
            )
            out.append(self.apply(fill))
        return out
