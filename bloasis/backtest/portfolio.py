"""SimulatedPortfolio — in-memory cash + positions for backtests.

Tracks cash, average cost, and current price per symbol. `mark()` updates
position values from the latest bar so `total_equity()` is always current.

SL/TP enforcement happens here too: `check_stops()` returns implicit SELL
fills when a held bar's high/low touches the stored stop or take-profit
levels. This mirrors what a broker would do for resting OCO orders.

PR49 — implements the `BrokerAdapter` protocol so the same per-step
runner code drives backtest (executor=SimulatedPortfolio) and live
(executor=AlpacaBrokerAdapter). When `data_panel` + `execution_cfg`
are provided, `place_market_order` simulates fills against next-day
bars internally; when omitted (legacy callers), `apply` is still the
direct entry point.

All state is in-memory; the engine persists to `equity_curve` and `trades`
tables via `bloasis/storage/writers.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Literal

import pandas as pd

if TYPE_CHECKING:
    from bloasis.broker.protocols import (
        AccountInfo,
        BrokerOrder,
        BrokerPosition,
        OrderResult,
    )
    from bloasis.config.schema import ExecutionConfig


def _to_dt_from_ts(value: object) -> datetime:
    """Convert a pandas Timestamp / numpy datetime to a tz-aware datetime."""
    ts = pd.Timestamp(value)  # type: ignore[arg-type]
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.to_pydatetime()


def _signal_ts_for_panel(signal_date: date, bars: pd.DataFrame | None) -> pd.Timestamp:
    """Build a Timestamp for `signal_date` matching the panel's tz convention.

    The engine strips tz from all data indices (`_normalize_tz`) for naive
    comparison, but tests / live caches may keep UTC-aware indices. Detect
    and match so `bars.index <= signal_ts` works in both cases.
    """
    naive = pd.Timestamp(signal_date.year, signal_date.month, signal_date.day)
    if bars is None or bars.empty or not isinstance(bars.index, pd.DatetimeIndex):
        return naive
    if bars.index.tz is None:
        return naive
    return naive.tz_localize(bars.index.tz)


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
    """Long-only simulated portfolio.

    PR49 — also implements the `BrokerAdapter` protocol so the strategy
    runner can drive both backtest and live with the same code. The
    `data_panel` / `execution_cfg` / `sectors` kwargs are optional for
    backwards-compatibility with callers that only use `apply()` /
    `mark()` / `check_stops()` directly.
    """

    initial_capital: float
    data_panel: dict[str, pd.DataFrame] | None = None
    execution_cfg: ExecutionConfig | None = None
    sectors: dict[str, str | None] | None = None
    cash: float = field(init=False)
    positions: dict[str, Position] = field(init=False)
    trade_count: int = field(init=False, default=0)
    realized_pnl_total: float = field(init=False, default=0.0)
    win_count: int = field(init=False, default=0)
    loss_count: int = field(init=False, default=0)
    _current_date: date | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.cash = float(self.initial_capital)
        self.positions = {}

    # ------------------------------------------------------------------
    # BrokerAdapter protocol (PR49)
    # ------------------------------------------------------------------

    @property
    def mode(self) -> Literal["paper", "live", "offline"]:
        return "offline"

    def advance_clock(self, signal_date: date) -> None:
        """Set the date stamp used by `place_market_order` to look up
        next-day bars for fill simulation. Called once per strategy step
        by the runner.
        """
        self._current_date = signal_date

    def get_account(self) -> AccountInfo:
        from bloasis.broker.protocols import AccountInfo

        equity = self.total_equity()
        return AccountInfo(cash=self.cash, equity=equity, buying_power=self.cash)

    def get_positions(self) -> list[BrokerPosition]:
        from bloasis.broker.protocols import BrokerPosition

        return [
            BrokerPosition(
                symbol=p.symbol,
                quantity=p.quantity,
                avg_cost=p.avg_cost,
                current_price=p.last_price,
                market_value=p.quantity * p.last_price,
            )
            for p in self.positions.values()
        ]

    def cancel_order(self, order_id: str) -> bool:
        """SimulatedPortfolio fills synchronously — there's nothing to cancel."""
        return False

    def place_market_order(self, order: BrokerOrder) -> OrderResult:
        """Simulate a market order against the next-day bar from `data_panel`.

        Requires both `data_panel` and `execution_cfg` to be set on the
        portfolio. The runner ensures this; legacy direct callers still
        use `apply()` instead.
        """
        from bloasis.broker.protocols import OrderResult

        if self.data_panel is None or self.execution_cfg is None:
            raise RuntimeError(
                "SimulatedPortfolio.place_market_order requires data_panel "
                "and execution_cfg at construction time"
            )
        if self._current_date is None:
            raise RuntimeError("SimulatedPortfolio.place_market_order called before advance_clock")

        bars = self.data_panel.get(order.symbol)
        sector = self.sectors.get(order.symbol) if self.sectors else None
        signal_ts = _signal_ts_for_panel(self._current_date, bars)
        submitted_at = datetime.now(tz=UTC)
        order_id = f"sim-{uuid.uuid4().hex[:12]}"

        if bars is None or bars.empty:
            return OrderResult(
                order_id=order_id,
                client_order_id=order.client_order_id,
                status="rejected",
                filled_qty=0.0,
                filled_avg_price=0.0,
                submitted_at=submitted_at,
                reason="no bars available",
            )

        if order.side == "buy":
            fill = self._simulate_buy_fill(order, bars, signal_ts, sector)
        else:
            fill = self._simulate_sell_fill(order, bars, signal_ts, sector)

        if fill is None:
            return OrderResult(
                order_id=order_id,
                client_order_id=order.client_order_id,
                status="rejected",
                filled_qty=0.0,
                filled_avg_price=0.0,
                submitted_at=submitted_at,
                reason="no fill bar available",
            )

        applied = self.apply(fill)
        return OrderResult(
            order_id=order_id,
            client_order_id=order.client_order_id,
            status="filled",
            filled_qty=applied.quantity,
            filled_avg_price=applied.price,
            submitted_at=submitted_at,
        )

    def _simulate_buy_fill(
        self,
        order: BrokerOrder,
        bars: pd.DataFrame,
        signal_ts: pd.Timestamp,
        sector: str | None,
    ) -> Fill | None:
        """Replicate FillSimulator.simulate_buy logic for use inside the
        portfolio. signal_close comes from the bar at signal_date, fill
        executes on the next bar's open price (with execution_cfg slippage).
        """
        assert self.execution_cfg is not None
        cfg = self.execution_cfg
        signal_idx = bars.index[bars.index <= signal_ts]
        if len(signal_idx) == 0:
            return None
        signal_close = float(bars.loc[signal_idx[-1], "close"])
        forward = bars.loc[bars.index > signal_idx[-1]]
        if forward.empty:
            return None

        if cfg.fill_mode == "market":
            next_bar = forward.iloc[0]
            open_price = float(next_bar["open"])
            slippage = open_price * cfg.market_slippage_bps / 10_000
            executed = open_price + slippage
            return Fill(
                timestamp=_to_dt_from_ts(next_bar.name),
                symbol=order.symbol,
                side="buy",
                quantity=order.qty,
                price=executed,
                fees=order.qty * executed * cfg.fees_bps / 10_000,
                slippage_bps=cfg.market_slippage_bps,
                sector=sector,
            )

        # limit_with_fallback
        limit_price = signal_close * (1 - cfg.limit_offset_bps / 10_000)
        timeout = max(1, cfg.limit_timeout_bars)
        candidate_bars = forward.iloc[:timeout]
        for ts, bar in candidate_bars.iterrows():
            low = float(bar["low"])
            if low <= limit_price:
                return Fill(
                    timestamp=_to_dt_from_ts(ts),
                    symbol=order.symbol,
                    side="buy",
                    quantity=order.qty,
                    price=limit_price,
                    fees=order.qty * limit_price * cfg.fees_bps / 10_000,
                    slippage_bps=0.0,
                    sector=sector,
                )

        # Fallback: market fill on bar after limit window expired.
        fallback_bars = forward.iloc[timeout : timeout + 1]
        if fallback_bars.empty:
            return None
        next_bar = fallback_bars.iloc[0]
        open_price = float(next_bar["open"])
        slippage = open_price * cfg.market_slippage_bps / 10_000
        executed = open_price + slippage
        return Fill(
            timestamp=_to_dt_from_ts(next_bar.name),
            symbol=order.symbol,
            side="buy",
            quantity=order.qty,
            price=executed,
            fees=order.qty * executed * cfg.fees_bps / 10_000,
            slippage_bps=cfg.market_slippage_bps,
            sector=sector,
        )

    def _simulate_sell_fill(
        self,
        order: BrokerOrder,
        bars: pd.DataFrame,
        signal_ts: pd.Timestamp,
        sector: str | None,
    ) -> Fill | None:
        """Mirror Backtester._execute_sell — sell at next-day open with
        market slippage."""
        assert self.execution_cfg is not None
        cfg = self.execution_cfg
        forward = bars.loc[bars.index > signal_ts]
        if forward.empty:
            return None
        next_bar = forward.iloc[0]
        open_price = float(next_bar["open"])
        slippage = open_price * cfg.market_slippage_bps / 10_000
        executed = open_price - slippage
        return Fill(
            timestamp=_to_dt_from_ts(next_bar.name),
            symbol=order.symbol,
            side="sell",
            quantity=order.qty,
            price=executed,
            fees=order.qty * executed * cfg.fees_bps / 10_000,
            slippage_bps=cfg.market_slippage_bps,
            sector=sector,
        )

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
