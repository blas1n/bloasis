"""Tests for `bloasis.backtest.fills.FillSimulator`."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from bloasis.backtest.fills import FillSimulator
from bloasis.config import ExecutionConfig


def _bars(values: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """values is list of (open, high, low, close)."""
    idx = pd.date_range("2024-01-02", periods=len(values), freq="B", tz="UTC")
    return pd.DataFrame(
        values,
        index=idx,
        columns=["open", "high", "low", "close"],
    )


SIGNAL_DATE = datetime(2024, 1, 2, tzinfo=UTC)


def test_market_fill_uses_next_bar_open_with_slippage() -> None:
    cfg = ExecutionConfig(fill_mode="market", market_slippage_bps=10, fees_bps=0)
    sim = FillSimulator(cfg)
    bars = _bars([(100, 101, 99, 100), (102, 103, 101, 102)])
    fill = sim.simulate_buy(
        symbol="X",
        quantity=10,
        signal_date=SIGNAL_DATE,
        signal_close=100.0,
        bars=bars,
    )
    assert fill is not None
    # next bar open = 102; slippage 10bps adds 0.102
    assert fill.price == pytest.approx(102.0 + 102 * 10 / 10_000, abs=1e-6)
    assert fill.side == "buy"


def test_market_fill_returns_none_at_eod() -> None:
    cfg = ExecutionConfig(fill_mode="market")
    sim = FillSimulator(cfg)
    bars = _bars([(100, 101, 99, 100)])  # only one bar, signal_date is its index
    fill = sim.simulate_buy(
        symbol="X",
        quantity=10,
        signal_date=SIGNAL_DATE,
        signal_close=100.0,
        bars=bars,
    )
    assert fill is None


def test_limit_fill_executes_when_low_touches() -> None:
    cfg = ExecutionConfig(
        fill_mode="limit_with_fallback",
        limit_offset_bps=100,  # 1%
        limit_timeout_bars=1,
    )
    sim = FillSimulator(cfg)
    # Limit price = 100 * (1 - 0.01) = 99. Next bar's low is 98 → fills.
    bars = _bars([(100, 101, 99, 100), (101, 102, 98, 101)])
    fill = sim.simulate_buy(
        symbol="X",
        quantity=10,
        signal_date=SIGNAL_DATE,
        signal_close=100.0,
        bars=bars,
    )
    assert fill is not None
    assert fill.price == pytest.approx(99.0)


def test_limit_fill_fallback_to_market_after_timeout() -> None:
    cfg = ExecutionConfig(
        fill_mode="limit_with_fallback",
        limit_offset_bps=10,  # tight: limit at 99.9
        limit_timeout_bars=1,
        market_slippage_bps=5,
    )
    sim = FillSimulator(cfg)
    # Limit at 99.9. Bar 1 low=99.95 (no fill). Bar 2 (fallback) opens at 102.
    bars = _bars(
        [
            (100, 101, 99, 100),  # signal
            (101, 102, 99.95, 101),  # bar 1 — limit not hit
            (102, 103, 101, 102),  # bar 2 — market fallback at open 102
        ]
    )
    fill = sim.simulate_buy(
        symbol="X",
        quantity=10,
        signal_date=SIGNAL_DATE,
        signal_close=100.0,
        bars=bars,
    )
    assert fill is not None
    expected = 102.0 + 102.0 * 5 / 10_000
    assert fill.price == pytest.approx(expected, abs=1e-6)


def test_fees_added_to_fill() -> None:
    cfg = ExecutionConfig(fill_mode="market", market_slippage_bps=0, fees_bps=10)
    sim = FillSimulator(cfg)
    bars = _bars([(100, 101, 99, 100), (100, 101, 99, 100)])
    fill = sim.simulate_buy(
        symbol="X",
        quantity=10,
        signal_date=SIGNAL_DATE,
        signal_close=100.0,
        bars=bars,
    )
    assert fill is not None
    expected_fees = fill.quantity * fill.price * 10 / 10_000
    assert fill.fees == pytest.approx(expected_fees)
