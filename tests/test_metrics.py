"""Tests for `bloasis.backtest.metrics`."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from bloasis.backtest.metrics import (
    alpha_annualized,
    annualized_return,
    information_ratio,
    max_drawdown,
    months_beating_benchmark,
    safe_ratio,
    sharpe_ratio,
    sortino_ratio,
    total_return,
)


def _equity(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


def test_total_return_zero_when_empty() -> None:
    assert total_return(_equity([])) == 0.0


def test_total_return_basic() -> None:
    assert total_return(_equity([100.0, 110.0])) == pytest.approx(0.10)


def test_annualized_return_handles_short_series() -> None:
    assert annualized_return(_equity([100.0])) == 0.0


def test_annualized_return_full_year_doubles() -> None:
    """100 → 200 over 252 trading days = +100% annualized."""
    val = annualized_return(_equity([100.0] + [200.0] * 251))
    assert val == pytest.approx(1.0, rel=0.05)


def test_sharpe_zero_for_constant_series() -> None:
    assert sharpe_ratio(_equity([100.0] * 50)) == 0.0


def test_sharpe_finite_for_random_walk() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    values = [100.0]
    for _ in range(252):
        values.append(values[-1] * (1 + rng.normal(0.0005, 0.01)))
    s = sharpe_ratio(_equity(values))
    assert math.isfinite(s)


def test_sortino_zero_for_constant() -> None:
    assert sortino_ratio(_equity([100.0] * 30)) == 0.0


def test_max_drawdown_basic() -> None:
    eq = _equity([100, 120, 110, 130, 90, 100])
    # Peak 130, trough 90 → -30/130 = -0.2308
    dd = max_drawdown(eq)
    assert dd == pytest.approx(-(130.0 - 90.0) / 130.0, abs=1e-6)


def test_max_drawdown_zero_for_monotone_up() -> None:
    eq = _equity([100, 110, 120, 130])
    assert max_drawdown(eq) == 0.0


def test_alpha_annualized_subtracts_benchmark() -> None:
    eq = _equity([100.0, 110.0, 120.0, 130.0, 140.0])
    bench = _equity([100.0, 105.0, 110.0, 115.0, 120.0])
    a = alpha_annualized(eq, bench)
    assert a > 0  # strategy beat benchmark


def test_information_ratio_zero_when_returns_match() -> None:
    eq = _equity([100.0, 110.0, 120.0])
    assert information_ratio(eq, eq) == 0.0


def test_months_beating_benchmark() -> None:
    """Build a year of daily data where strategy beats benchmark every month."""
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    eq = pd.Series([100.0 * (1.001**i) for i in range(252)], index=idx)
    bench = pd.Series([100.0 * (1.0005**i) for i in range(252)], index=idx)
    beat, total = months_beating_benchmark(eq, bench)
    assert total > 0
    assert beat == total  # strategy outperformed every month


def test_safe_ratio_handles_zero_and_nan() -> None:
    assert safe_ratio(1.0, 0.0) == 0.0
    assert safe_ratio(1.0, float("nan")) == 0.0
    assert safe_ratio(float("inf"), 1.0) == 0.0
    assert safe_ratio(2.0, 4.0) == 0.5
