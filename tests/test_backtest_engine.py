"""End-to-end test for `Backtester` with synthetic data.

Builds a tiny multi-symbol panel that's predictable enough to verify the
engine wires together correctly: data → features → composites → score →
signals → fills → portfolio → metrics → acceptance.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from bloasis.backtest import BacktestData, Backtester
from bloasis.config import StrategyConfig


def _synthetic_bars(
    n_days: int,
    *,
    seed: int,
    drift: float = 0.0005,
    sigma: float = 0.01,
    start: str = "2020-01-01",
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n_days, freq="B")
    closes = [100.0]
    for _ in range(n_days - 1):
        ret = rng.normal(drift, sigma)
        closes.append(closes[-1] * (1 + ret))
    closes_arr = np.array(closes)
    open_arr = closes_arr * (1 - 0.001)
    high = closes_arr * (1 + abs(rng.normal(0, sigma * 0.3, n_days)))
    low = closes_arr * (1 - abs(rng.normal(0, sigma * 0.3, n_days)))
    volume = rng.integers(1_000_000, 5_000_000, n_days).astype(float)
    return pd.DataFrame(
        {
            "open": open_arr,
            "high": high,
            "low": low,
            "close": closes_arr,
            "volume": volume,
        },
        index=idx,
    )


def _backtest_data(n_days: int = 600) -> BacktestData:
    """Build a 4-symbol synthetic panel + market context."""
    bars = {
        "AAPL": _synthetic_bars(n_days, seed=1, drift=0.0008),
        "MSFT": _synthetic_bars(n_days, seed=2, drift=0.0006),
        "GOOG": _synthetic_bars(n_days, seed=3, drift=0.0004),
        "META": _synthetic_bars(n_days, seed=4, drift=0.0002),
    }
    spy = _synthetic_bars(n_days, seed=99, drift=0.0005)
    vix_idx = bars["AAPL"].index
    vix = pd.Series(
        20.0 + np.random.default_rng(7).normal(0, 2, len(vix_idx)),
        index=vix_idx,
        name="vix",
    )
    return BacktestData(
        symbols=["AAPL", "MSFT", "GOOG", "META"],
        bars=bars,
        vix_series=vix,
        spy_close_series=spy["close"],
        sectors={"AAPL": "Tech", "MSFT": "Tech", "GOOG": "Tech", "META": "Tech"},
    )


def test_backtester_runs_end_to_end_and_produces_result() -> None:
    """Smoke test: backtester completes a degenerate fold without exceptions."""
    cfg = StrategyConfig()
    data = _backtest_data(n_days=400)
    bt = Backtester(cfg, data)
    result = bt.run(
        start=date(2021, 6, 1),
        end=date(2021, 12, 1),
        train_days=120,
        test_days=30,
        step_days=30,
    )
    assert result.n_folds >= 1
    assert all(f.test_start < f.test_end for f in result.fold_results)
    assert result.initial_capital == cfg.execution.initial_capital


def test_backtester_acceptance_evaluation_runs() -> None:
    cfg = StrategyConfig()
    data = _backtest_data(n_days=400)
    bt = Backtester(cfg, data)
    result = bt.run(
        start=date(2021, 6, 1),
        end=date(2021, 12, 1),
        train_days=120,
        test_days=30,
        step_days=30,
    )
    # AcceptanceEvaluator always returns a list of reasons (one per criterion).
    assert len(result.acceptance_reasons) == 4
    assert isinstance(result.passed_acceptance, bool)


def test_backtester_invalid_period_raises() -> None:
    import pytest

    cfg = StrategyConfig()
    data = _backtest_data(n_days=300)
    bt = Backtester(cfg, data)
    with pytest.raises(ValueError, match="start"):
        bt.run(start=date(2024, 1, 1), end=date(2024, 1, 1))


def test_backtester_with_empty_bars_yields_no_trades() -> None:
    """Universe with no fetchable bars → engine completes with 0 trades."""
    cfg = StrategyConfig()
    data = BacktestData(
        symbols=["A", "B"],
        bars={
            "A": pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []}),
            "B": pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []}),
        },
        vix_series=pd.Series(
            [20.0],
            index=pd.date_range("2020-01-01", periods=1, freq="D"),
            name="vix",
        ),
        spy_close_series=pd.Series(
            [400.0],
            index=pd.date_range("2020-01-01", periods=1, freq="D"),
            name="spy",
        ),
    )
    bt = Backtester(cfg, data)
    # Test window outside SPY index → degenerate empty fold.
    result = bt.run(
        start=date(2024, 1, 1),
        end=date(2024, 6, 1),
        train_days=30,
        test_days=10,
    )
    assert result.n_trades_total == 0
