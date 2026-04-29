"""StrategyComposer — splits capital across allocation legs.

Per `docs/mission.md`, the M2 mission's safety net is "70% SPY + 30%
strategy". The composer makes that split explicit:

    For each AllocationStrategy in cfg.allocation.strategies:
      - spy_passive: target_dollars = total_capital * weight
                     -> single BUY of SPY shares
      - strategy:    target_dollars = total_capital * weight
                     -> hand off to the existing signal pipeline,
                        which sizes individual picks within this slice

Backtest engine doesn't use the composer — there it's the strategy
running solo (alpha measured neat). Live trading uses it so the worst-case
underperformance is bounded by the strategy's weight.
"""

from __future__ import annotations

from dataclasses import dataclass

from bloasis.config import AllocationConfig, AllocationStrategy

SPY_SYMBOL = "SPY"


@dataclass(frozen=True, slots=True)
class AllocationLeg:
    """One slice of capital with its assigned strategy type."""

    name: str
    strategy_type: str  # "spy_passive" | "strategy"
    capital: float


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Per-leg capital + the SPY share count for the passive leg.

    `spy_share_qty` is None when there's no spy_passive leg or SPY price
    is unavailable. The CLI uses this directly for the broker's BUY SPY
    market order.
    """

    legs: tuple[AllocationLeg, ...]
    spy_share_qty: float | None
    strategy_capital: float  # combined capital for "strategy" type legs
    total_capital: float


class StrategyComposer:
    """Pure compute — no I/O. Build an `ExecutionPlan` from config + state."""

    def __init__(self, cfg: AllocationConfig) -> None:
        self._cfg = cfg

    def plan(
        self,
        *,
        total_capital: float,
        spy_price: float | None,
    ) -> ExecutionPlan:
        """Translate `total_capital` into per-leg dollar allocations.

        If `cfg.allocation.strategies` is empty, the entire capital goes
        to the implicit "strategy" leg — i.e., the user opted out of the
        safety net and runs the strategy 100%.
        """
        legs: list[AllocationLeg] = []
        strategy_capital = 0.0
        spy_capital = 0.0

        if not self._cfg.strategies:
            legs.append(
                AllocationLeg(
                    name="strategy",
                    strategy_type="strategy",
                    capital=total_capital,
                )
            )
            strategy_capital = total_capital
        else:
            for s in self._cfg.strategies:
                cap = total_capital * s.weight
                legs.append(
                    AllocationLeg(
                        name=s.name,
                        strategy_type=s.type,
                        capital=cap,
                    )
                )
                if s.type == "strategy":
                    strategy_capital += cap
                elif s.type == "spy_passive":
                    spy_capital += cap

        spy_qty: float | None = None
        if spy_capital > 0 and spy_price is not None and spy_price > 0:
            spy_qty = spy_capital / spy_price

        return ExecutionPlan(
            legs=tuple(legs),
            spy_share_qty=spy_qty,
            strategy_capital=strategy_capital,
            total_capital=total_capital,
        )

    @staticmethod
    def has_spy_leg(cfg: AllocationConfig) -> bool:
        return any(s.type == "spy_passive" for s in cfg.strategies)


def make_composer(cfg: AllocationConfig | AllocationStrategy) -> StrategyComposer:
    """Convenience constructor accepting either AllocationConfig or a single
    AllocationStrategy (wrapped automatically)."""
    if isinstance(cfg, AllocationStrategy):
        return StrategyComposer(AllocationConfig(strategies=[cfg]))
    return StrategyComposer(cfg)
