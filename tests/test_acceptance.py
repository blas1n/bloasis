"""Tests for `bloasis.backtest.acceptance.AcceptanceEvaluator`."""

from __future__ import annotations

from datetime import date

import pandas as pd

from bloasis.backtest.acceptance import AcceptanceEvaluator
from bloasis.backtest.result import BacktestResult, FoldResult
from bloasis.config import AcceptanceCriteria


def _empty_curve() -> pd.Series:
    return pd.Series([1.0], index=pd.date_range("2024-01-01", periods=1), dtype=float)


def _result(
    *,
    n_folds: int,
    median_alpha: float = 0.0,
    median_sharpe: float = 1.0,
    median_dd_ratio: float = 0.5,
) -> BacktestResult:
    folds = [
        FoldResult(
            fold_index=i,
            train_start=date(2020, 1, 1),
            train_end=date(2023, 1, 1),
            test_start=date(2023, 1, 2),
            test_end=date(2024, 1, 1),
            final_equity=11_000,
            spy_final_equity=10_500,
            total_return=0.1,
            spy_total_return=0.05,
            annualized_return=0.1,
            annualized_alpha=0.05,
            sharpe=1.2,
            spy_sharpe=1.0,
            sortino=1.5,
            max_drawdown=-0.10,
            spy_max_drawdown=-0.20,
            max_dd_ratio_to_spy=0.5,
            win_rate=0.55,
            n_trades=10,
            months_beating_spy=7,
            months_total=12,
            equity_curve=_empty_curve(),
        )
        for i in range(n_folds)
    ]
    return BacktestResult(
        run_id=0,
        config_hash="abc",
        start_date=date(2020, 1, 1),
        end_date=date(2024, 1, 1),
        initial_capital=10_000,
        fold_results=folds,
        median_alpha_annualized=median_alpha,
        median_sharpe_vs_spy=median_sharpe,
        median_max_dd_ratio_to_spy=median_dd_ratio,
        median_total_return=0.1,
        median_spy_total_return=0.05,
        median_win_rate=0.55,
        median_months_beating_spy_pct=0.6,
        n_folds=n_folds,
        n_trades_total=10 * n_folds,
    )


def test_passes_when_all_criteria_met() -> None:
    crit = AcceptanceCriteria(
        walk_forward_min_folds=3,
        median_alpha_annualized=0.0,
        median_sharpe_vs_spy=1.0,
        median_max_dd_ratio_to_spy=0.85,
    )
    evaluator = AcceptanceEvaluator(crit)
    result = _result(n_folds=5, median_alpha=0.02, median_sharpe=1.1, median_dd_ratio=0.5)
    decision = evaluator.evaluate(result)
    assert decision.passed is True
    assert all(r.startswith("PASS") for r in decision.reasons)


def test_fails_when_too_few_folds() -> None:
    crit = AcceptanceCriteria(walk_forward_min_folds=5)
    evaluator = AcceptanceEvaluator(crit)
    result = _result(n_folds=2)
    decision = evaluator.evaluate(result)
    assert decision.passed is False
    assert any("folds" in r and r.startswith("FAIL") for r in decision.reasons)


def test_fails_when_alpha_below_threshold() -> None:
    crit = AcceptanceCriteria(median_alpha_annualized=0.01)
    evaluator = AcceptanceEvaluator(crit)
    result = _result(n_folds=5, median_alpha=-0.05)
    decision = evaluator.evaluate(result)
    assert decision.passed is False
    assert any("alpha" in r.lower() for r in decision.reasons)


def test_fails_when_dd_ratio_too_large() -> None:
    crit = AcceptanceCriteria(median_max_dd_ratio_to_spy=0.85)
    evaluator = AcceptanceEvaluator(crit)
    result = _result(n_folds=5, median_dd_ratio=1.2)
    decision = evaluator.evaluate(result)
    assert decision.passed is False
    assert any("dd_ratio" in r.lower() for r in decision.reasons)


def test_partial_failure_still_reports_each_check() -> None:
    """Even on failure, every criterion reports PASS or FAIL — no early exit."""
    crit = AcceptanceCriteria(walk_forward_min_folds=10)
    evaluator = AcceptanceEvaluator(crit)
    result = _result(n_folds=2, median_alpha=0.05, median_sharpe=1.5)
    decision = evaluator.evaluate(result)
    assert len(decision.reasons) == 4  # one per criterion
