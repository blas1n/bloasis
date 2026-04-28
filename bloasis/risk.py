"""Deterministic risk rules.

All risk decisions live here so the same code path runs in live and
backtest. Rules are evaluated in order; the first matching rule wins.

VIX-based de-risking is the most important rule for the M2 mission
(SPY-parity with lower drawdown — see `docs/mission.md`).

Limitations:
- Sector concentration requires the caller to pass current sector
  exposure as a fraction of portfolio. The risk evaluator does not query
  the portfolio itself; that is the caller's responsibility (CLI passes
  empty dict; backtest engine populates from simulated positions).
- All rules are long-only aware. Short selling is a Phase 4 question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from bloasis.config import RiskConfig
from bloasis.signal import TradingSignal

RiskAction = Literal["APPROVE", "REJECT", "ADJUST"]


@dataclass(frozen=True, slots=True)
class PortfolioState:
    """Per-evaluation snapshot of portfolio sector exposure.

    `sector_concentrations` maps sector name to fraction of total
    portfolio value (0.0 .. 1.0). Sectors not in the dict are treated as
    zero exposure. `total_value` is informational; rules that scale by it
    use `target_size_pct` directly.
    """

    total_value: float = 0.0
    sector_concentrations: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketState:
    """Per-evaluation market snapshot. VIX is the only consumed field today."""

    timestamp: datetime
    vix: float


@dataclass(frozen=True, slots=True)
class RiskDecision:
    action: RiskAction
    adjusted_size_pct: float | None = None
    reasons: tuple[str, ...] = ()


class RiskEvaluator:
    """Apply VIX cutoff, single-order cap, and sector concentration rules."""

    def __init__(self, cfg: RiskConfig) -> None:
        self._cfg = cfg

    def evaluate(
        self,
        signal: TradingSignal,
        portfolio: PortfolioState,
        market: MarketState,
    ) -> RiskDecision:
        # SELL signals always pass — closing risk is reducing it.
        if signal.action == "SELL":
            return RiskDecision(action="APPROVE", adjusted_size_pct=0.0)

        if signal.action == "HOLD":
            return RiskDecision(action="APPROVE")

        reasons: list[str] = []
        size = signal.target_size_pct

        # Rule 1: extreme VIX blocks new BUYs outright.
        if market.vix > self._cfg.vix_extreme:
            return RiskDecision(
                action="REJECT",
                reasons=(f"VIX {market.vix:.1f} > extreme {self._cfg.vix_extreme:.1f}",),
            )

        # Rule 2: high VIX halves the target size.
        if market.vix > self._cfg.vix_high:
            size *= 0.5
            reasons.append(f"VIX {market.vix:.1f} > high {self._cfg.vix_high:.1f}: size halved")

        # Rule 3: cap single-order size.
        if size > self._cfg.max_single_order_pct:
            reasons.append(f"capped at single-order max {self._cfg.max_single_order_pct:.2%}")
            size = self._cfg.max_single_order_pct

        # Rule 4: sector concentration. After this BUY, the sector exposure
        # must remain at or below `max_sector_concentration`.
        sector = signal.sector or "_unknown"
        existing = portfolio.sector_concentrations.get(sector, 0.0)
        if existing + size > self._cfg.max_sector_concentration:
            allowed = self._cfg.max_sector_concentration - existing
            if allowed <= 0:
                return RiskDecision(
                    action="REJECT",
                    reasons=(
                        *reasons,
                        f"sector '{sector}' already at "
                        f"{existing:.2%} >= cap {self._cfg.max_sector_concentration:.2%}",
                    ),
                )
            reasons.append(
                f"sector '{sector}' clipped from {size:.2%} to {allowed:.2%} "
                f"(existing {existing:.2%}, cap {self._cfg.max_sector_concentration:.2%})"
            )
            size = allowed

        if size <= 0:
            return RiskDecision(action="REJECT", reasons=tuple(reasons or ("size <= 0",)))

        if size != signal.target_size_pct:
            return RiskDecision(
                action="ADJUST",
                adjusted_size_pct=size,
                reasons=tuple(reasons),
            )
        return RiskDecision(action="APPROVE", adjusted_size_pct=size, reasons=tuple(reasons))
