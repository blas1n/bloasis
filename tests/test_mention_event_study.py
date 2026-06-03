"""Tests for the mention event-study decomposition (PR55).

The headline metric from the user's gap insight: for an event at date T
(entry = T's open), decompose the impact into

  gap         = open[T]  / close[T-1] − 1     ← HFT-captured (pre-market)
  intraday    = close[T] / open[T]    − 1     ← available from open
  forward     = close[T+h] / open[T]  − 1     ← post-open continuation

If gap dominates the total move, the retail edge has already been taken.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from bloasis.analysis.mention_event_study import (
    compute_baseline_forward,
    decompose_event_return,
    summarize_decomposed,
)


def _bars() -> pd.DataFrame:
    """Mini bar panel with explicit open/close on consecutive trading days."""
    return pd.DataFrame(
        {
            "open": [100.0, 110.0, 113.0, 115.0, 118.0, 120.0],
            "close": [102.0, 112.0, 114.0, 117.0, 119.0, 122.0],
        },
        index=pd.DatetimeIndex(
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05", "2026-06-08"],
            tz="UTC",
        ),
    )


def test_decompose_event_return_basic() -> None:
    bars = _bars()
    # Entry on 2026-06-02. prev close = 102, open = 110, close = 112.
    # gap = 110/102 - 1 ≈ 0.0784
    # intraday = 112/110 - 1 ≈ 0.0182
    # forward 2d = close[2026-06-04] / open[2026-06-02] - 1 = 117/110 - 1 ≈ 0.0636
    res = decompose_event_return(bars, entry_date=date(2026, 6, 2), horizon=2)
    assert res is not None
    assert res["gap"] == pytest.approx(110 / 102 - 1)
    assert res["intraday"] == pytest.approx(112 / 110 - 1)
    assert res["forward"] == pytest.approx(117 / 110 - 1)
    # total move from prev close to T+h close
    assert res["total"] == pytest.approx(117 / 102 - 1)


def test_decompose_event_return_returns_none_without_prev_close() -> None:
    bars = _bars()
    # Entry at the FIRST bar: no prev_close to anchor the gap.
    assert decompose_event_return(bars, entry_date=date(2026, 6, 1), horizon=2) is None


def test_decompose_event_return_returns_none_without_forward_bar() -> None:
    bars = _bars()
    # Last bar (2026-06-08): no +2 forward bars.
    assert decompose_event_return(bars, entry_date=date(2026, 6, 8), horizon=2) is None


def test_decompose_event_return_skips_when_date_not_in_index() -> None:
    bars = _bars()
    # Saturday — not a trading bar.
    assert decompose_event_return(bars, entry_date=date(2026, 6, 6), horizon=2) is None


# ---------------------------------------------------------------------------
# summarize_decomposed — gap-fraction = HFT-vs-retail split
# ---------------------------------------------------------------------------


def test_summarize_decomposed_basic_stats() -> None:
    rows = [
        {"gap": 0.05, "intraday": 0.01, "forward": 0.02, "total": 0.08},
        {"gap": 0.03, "intraday": 0.00, "forward": 0.01, "total": 0.04},
        {"gap": -0.01, "intraday": 0.00, "forward": -0.01, "total": -0.02},
    ]
    s = summarize_decomposed(rows)
    assert s["n"] == 3
    assert s["mean_gap"] == pytest.approx((0.05 + 0.03 - 0.01) / 3)
    assert s["mean_intraday"] == pytest.approx((0.01 + 0.0 + 0.0) / 3)
    assert s["mean_forward"] == pytest.approx((0.02 + 0.01 - 0.01) / 3)
    assert s["mean_total"] == pytest.approx((0.08 + 0.04 - 0.02) / 3)
    # gap_fraction = mean_gap / mean_total when mean_total > 0
    assert s["gap_fraction"] == pytest.approx(s["mean_gap"] / s["mean_total"])


def test_summarize_decomposed_empty() -> None:
    s = summarize_decomposed([])
    assert s["n"] == 0
    assert s["mean_gap"] == 0.0
    assert s["gap_fraction"] == 0.0


def test_summarize_decomposed_zero_total_avoids_divzero() -> None:
    # All zero gaps and totals → gap_fraction defined as 0, not NaN.
    rows = [{"gap": 0.0, "intraday": 0.0, "forward": 0.0, "total": 0.0}]
    s = summarize_decomposed(rows)
    assert s["gap_fraction"] == 0.0


# ---------------------------------------------------------------------------
# PR56 — baseline (regime control) for the forward leg
#
# A positive mean forward return after Trump mentions doesn't prove a
# Trump-mention edge — over 2024-2026 a basket of AMZN/AAPL/META/NVDA
# drifted up regardless. The honest comparison is excess = event_forward
# − baseline_forward_of_same_ticker. compute_baseline_forward measures
# the per-ticker unconditional mean of close[T+h]/open[T]-1 over every
# valid trading day in the window.
# ---------------------------------------------------------------------------


def test_compute_baseline_forward_basic() -> None:
    """Mean over all valid (T, T+h) pairs of close[T+h]/open[T]-1."""
    bars = _bars()
    # horizon=1 → valid T's are positions 0..len-2 (5 of 6 bars). Per-T
    # forward = close[T+1] / open[T] - 1.
    h = 1
    expected = (
        (112 / 100 - 1) + (114 / 110 - 1) + (117 / 113 - 1) + (119 / 115 - 1) + (122 / 118 - 1)
    ) / 5
    assert compute_baseline_forward(bars, horizon=h) == pytest.approx(expected)


def test_compute_baseline_forward_horizon2() -> None:
    bars = _bars()
    # horizon=2 → valid T's are positions 0..len-3 (4 of 6 bars).
    h = 2
    expected = ((114 / 100 - 1) + (117 / 110 - 1) + (119 / 113 - 1) + (122 / 115 - 1)) / 4
    assert compute_baseline_forward(bars, horizon=h) == pytest.approx(expected)


def test_compute_baseline_forward_too_few_bars_returns_zero() -> None:
    """When len(bars) <= horizon, no valid forward window exists."""
    bars = pd.DataFrame(
        {"open": [100.0, 110.0], "close": [102.0, 112.0]},
        index=pd.DatetimeIndex(["2026-06-01", "2026-06-02"], tz="UTC"),
    )
    assert compute_baseline_forward(bars, horizon=2) == 0.0
    assert compute_baseline_forward(bars, horizon=5) == 0.0


def test_compute_baseline_forward_filters_zero_open() -> None:
    """Zero / negative opens must not produce inf or NaN baseline."""
    bars = pd.DataFrame(
        {
            "open": [100.0, 0.0, 113.0, 115.0],
            "close": [102.0, 112.0, 114.0, 117.0],
        },
        index=pd.DatetimeIndex(["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"], tz="UTC"),
    )
    # horizon=1: valid pairs are (T=0: 112/100), (T=2: 117/113). T=1 (open=0)
    # is filtered out.
    h = 1
    expected = ((112 / 100 - 1) + (117 / 113 - 1)) / 2
    assert compute_baseline_forward(bars, horizon=h) == pytest.approx(expected)


def test_summarize_decomposed_reports_mean_baseline_when_present() -> None:
    """If rows carry 'baseline', summary returns mean_baseline + mean_excess."""
    rows = [
        {"gap": 0.01, "intraday": 0.00, "forward": 0.05, "total": 0.06, "baseline": 0.02},
        {"gap": 0.02, "intraday": 0.00, "forward": 0.03, "total": 0.05, "baseline": 0.01},
    ]
    s = summarize_decomposed(rows)
    assert s["mean_baseline"] == pytest.approx(0.015)
    assert s["mean_excess"] == pytest.approx(s["mean_forward"] - s["mean_baseline"])


def test_summarize_decomposed_excess_absent_when_no_baseline() -> None:
    """Rows without 'baseline' key → no mean_baseline / mean_excess fields
    (preserves backward compat with v1 callers)."""
    rows = [{"gap": 0.01, "intraday": 0.00, "forward": 0.05, "total": 0.06}]
    s = summarize_decomposed(rows)
    assert "mean_baseline" not in s
    assert "mean_excess" not in s
