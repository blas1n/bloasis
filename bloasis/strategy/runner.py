"""Per-step strategy runner — single pipeline shared by backtest + live (PR49).

`execute_strategy_step` consumes pre-built candidates + a `BrokerAdapter`
executor and runs the post-candidate pipeline:

  signals -> tolerance band -> risk eval -> regime overlay -> orders

Both `Backtester._run_fold` (looping over trading days with
`SimulatedPortfolio` as executor) and `bloasis trade paper` (single-shot
with `AlpacaBrokerAdapter`) call this. Adding a knob to the post-candidate
pipeline now means changing one place; PR48's missing live-path scorer
dispatch was caught precisely because that earlier wiring was duplicated.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from bloasis.broker.protocols import BrokerAdapter, BrokerOrder, OrderResult
from bloasis.risk import MarketState, PortfolioState
from bloasis.signal import HeldPosition, TradingSignal

if TYPE_CHECKING:
    import pandas as pd

    from bloasis.config import StrategyConfig
    from bloasis.signal import CandidateData


PersistHook = Callable[[BrokerOrder, OrderResult, TradingSignal], None]


@dataclass(slots=True)
class StepResult:
    """One per-step run's emitted orders + bookkeeping for the next step."""

    signals: list[TradingSignal] = field(default_factory=list)
    submitted: list[tuple[BrokerOrder, OrderResult, TradingSignal]] = field(default_factory=list)
    new_buy_set: set[str] = field(default_factory=set)


def execute_strategy_step(
    *,
    cfg: StrategyConfig,
    candidates: list[CandidateData],
    held_positions: list[HeldPosition],
    market_state: MarketState,
    spy_returns_to_date: pd.Series,
    portfolio_state: PortfolioState,
    signal_date: datetime,
    executor: BrokerAdapter,
    prev_buy_set: set[str] | None = None,
    label: str = "step",
    persist_hook: PersistHook | None = None,
) -> StepResult:
    """Generate signals from candidates, run risk + overlay + sizing,
    submit BUY/SELL orders to the executor.

    Returns the submitted orders' results plus the per-step bookkeeping
    (`new_buy_set` for the caller's tolerance-band tracking).

    Stop-loss / take-profit checks and mark-to-market are NOT performed
    here — those are backtester-only steps that run after this returns.
    Live trading delegates SL/TP to broker bracket orders (future PR).
    """
    # Lazy imports so tests can monkeypatch SignalGenerator / RiskEvaluator
    # at the canonical location without binding to runner's namespace.
    from bloasis.risk import RiskEvaluator
    from bloasis.scoring.regime_overlay import (
        RegimeOverlayParams,
        compute_regime_scale,
    )
    from bloasis.signal import SignalGenerator

    sig_gen = SignalGenerator(cfg.scorer, cfg.signal)
    signals = sig_gen.generate(candidates, held=held_positions)

    # PR20 tolerance-band rebalancing — skip the BUY churn if today's
    # set differs from yesterday's by less than the configured fraction.
    # SELL signals always honored (avoid cash drag from drifted positions).
    rebalance_tolerance = cfg.signal.rebalance_tolerance_pct
    if rebalance_tolerance > 0 and prev_buy_set is not None:
        today_buy_set = {s.symbol for s in signals if s.action == "BUY"}
        union = prev_buy_set | today_buy_set
        if union:
            diff_frac = len(today_buy_set ^ prev_buy_set) / len(union)
            if diff_frac < rebalance_tolerance:
                signals = [s for s in signals if s.action == "SELL"]
    new_buy_set = {s.symbol for s in signals if s.action == "BUY"}

    # PR12 regime overlay — Barroso-Santa-Clara constant-vol + DM bear gate.
    overlay_params = RegimeOverlayParams(
        enabled=cfg.regime_overlay.enabled,
        sigma_target=cfg.regime_overlay.sigma_target,
        vol_lookback_days=cfg.regime_overlay.vol_lookback_days,
        bear_lookback_days=cfg.regime_overlay.bear_lookback_days,
        bear_scale=cfg.regime_overlay.bear_scale,
        scale_clip=cfg.regime_overlay.scale_clip,
    )
    regime_scale = compute_regime_scale(spy_returns_to_date, params=overlay_params)

    risk = RiskEvaluator(cfg.risk)
    account = executor.get_account()
    equity = account.equity
    held_qty_by_symbol = {p.symbol: p.quantity for p in executor.get_positions()}

    submitted: list[tuple[BrokerOrder, OrderResult, TradingSignal]] = []
    for sig in signals:
        decision = risk.evaluate(sig, portfolio_state, market_state)
        if decision.action == "REJECT":
            continue
        size_pct = (
            decision.adjusted_size_pct
            if decision.adjusted_size_pct is not None
            else sig.target_size_pct
        )

        if sig.action == "BUY":
            if sig.entry_price is None or sig.entry_price <= 0:
                continue
            sized = size_pct * regime_scale
            target_capital = equity * sized
            qty = target_capital / float(sig.entry_price)
            if qty <= 0:
                continue
            order = BrokerOrder(
                symbol=sig.symbol,
                side="buy",
                qty=qty,
                client_order_id=_make_client_id(label, "buy", sig.symbol, signal_date),
            )
        elif sig.action == "SELL":
            held_qty = held_qty_by_symbol.get(sig.symbol, 0.0)
            if held_qty <= 0:
                continue
            order = BrokerOrder(
                symbol=sig.symbol,
                side="sell",
                qty=held_qty,
                client_order_id=_make_client_id(label, "sell", sig.symbol, signal_date),
            )
        else:
            continue

        result = executor.place_market_order(order)
        submitted.append((order, result, sig))
        if persist_hook is not None:
            persist_hook(order, result, sig)

    return StepResult(
        signals=signals,
        submitted=submitted,
        new_buy_set=new_buy_set,
    )


def _make_client_id(label: str, side: str, symbol: str, signal_date: datetime) -> str:
    """Idempotent client_order_id used for broker dedupe + audit log linking.

    Format: bloasis-<label>-<side>-<symbol>-<unix>-<rand4> where unix is
    the signal_date's timestamp (so re-running the same date won't collide
    with a different one) and rand4 disambiguates within the second.
    """
    rand = uuid.uuid4().hex[:4]
    return f"bloasis-{label}-{side}-{symbol}-{int(signal_date.timestamp())}-{rand}"
