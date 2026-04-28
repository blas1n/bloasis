"""Acceptance gate evaluator.

Compare aggregated `BacktestResult` against `AcceptanceCriteria` from the
loaded config. The gate is the formal mechanism that promotes a config
between mission phases — a config with `passed_acceptance == False`
cannot be deployed to live trading (CLI enforces this in PR6).

Per the design (docs/mission.md), we evaluate against the **median** of
fold metrics, not the aggregate. This is more conservative than mean
and prevents a single lucky fold from carrying the run.
"""

from __future__ import annotations

from dataclasses import dataclass

from bloasis.backtest.result import BacktestResult
from bloasis.config import AcceptanceCriteria


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    passed: bool
    reasons: tuple[str, ...]


class AcceptanceEvaluator:
    """Apply each acceptance criterion to a BacktestResult."""

    def __init__(self, criteria: AcceptanceCriteria) -> None:
        self._c = criteria

    def evaluate(self, result: BacktestResult) -> AcceptanceResult:
        reasons: list[str] = []

        # 1. Walk-forward minimum folds.
        if result.n_folds < self._c.walk_forward_min_folds:
            reasons.append(f"FAIL  folds: {result.n_folds} < {self._c.walk_forward_min_folds}")
        else:
            reasons.append(f"PASS  folds: {result.n_folds} >= {self._c.walk_forward_min_folds}")

        # 2. Median alpha (annualized).
        if result.median_alpha_annualized < self._c.median_alpha_annualized:
            reasons.append(
                f"FAIL  median_alpha_annualized: "
                f"{result.median_alpha_annualized:+.4f} < {self._c.median_alpha_annualized:+.4f}"
            )
        else:
            reasons.append(
                f"PASS  median_alpha_annualized: "
                f"{result.median_alpha_annualized:+.4f} >= {self._c.median_alpha_annualized:+.4f}"
            )

        # 3. Median Sharpe vs SPY ratio (we want strategy.sharpe / spy.sharpe).
        if result.median_sharpe_vs_spy < self._c.median_sharpe_vs_spy:
            reasons.append(
                f"FAIL  median_sharpe_vs_spy: "
                f"{result.median_sharpe_vs_spy:.3f} < {self._c.median_sharpe_vs_spy:.3f}"
            )
        else:
            reasons.append(
                f"PASS  median_sharpe_vs_spy: "
                f"{result.median_sharpe_vs_spy:.3f} >= {self._c.median_sharpe_vs_spy:.3f}"
            )

        # 4. Max drawdown ratio to SPY (lower is better).
        observed_dd = result.median_max_dd_ratio_to_spy
        cap_dd = self._c.median_max_dd_ratio_to_spy
        if observed_dd > cap_dd:
            reasons.append(f"FAIL  median_max_dd_ratio_to_spy: {observed_dd:.3f} > {cap_dd:.3f}")
        else:
            reasons.append(f"PASS  median_max_dd_ratio_to_spy: {observed_dd:.3f} <= {cap_dd:.3f}")

        passed = all(r.startswith("PASS") for r in reasons)
        return AcceptanceResult(passed=passed, reasons=tuple(reasons))
