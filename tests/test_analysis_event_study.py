"""Tests for bloasis.analysis.event_study (PR54).

Two pure-compute event studies on daily closes:

  post-spike reversion — generalizes the "buy UBER on the earnings-call
    partnership news, watch it fall" case. After a big single-day move,
    what do the next N days do on average? If negative, chasing spikes
    is a statistically losing game.

  hub-earnings drift — Cohen-Frazzini economic-link lag. Around a hub
    stock's earnings dates, what do related stocks do over the next N
    days? Tests whether linked-name reactions are delayed (tradeable).
"""

from __future__ import annotations

import pandas as pd
import pytest

from bloasis.analysis.event_study import (
    find_spike_dates,
    forward_cum_returns,
    summarize_forward,
)


def _closes(values: list[float], start: str = "2026-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B", tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# find_spike_dates
# ---------------------------------------------------------------------------


def test_find_spike_dates_up_detects_big_jump() -> None:
    # day 2: +10% jump (100→110); others flat-ish.
    closes = _closes([100, 101, 111.1, 111, 112])
    spikes = find_spike_dates(closes, threshold=0.05, direction="up")
    # The +10% day (index 2) qualifies.
    assert len(spikes) == 1
    assert spikes[0] == closes.index[2]


def test_find_spike_dates_down_detects_crash() -> None:
    closes = _closes([100, 101, 90, 91, 92])  # day 2: -10.9%
    spikes = find_spike_dates(closes, threshold=0.05, direction="down")
    assert len(spikes) == 1
    assert spikes[0] == closes.index[2]


def test_find_spike_dates_up_ignores_down_moves() -> None:
    closes = _closes([100, 101, 90, 91, 92])  # only a down move
    assert find_spike_dates(closes, threshold=0.05, direction="up") == []


def test_find_spike_dates_both_directions() -> None:
    closes = _closes([100, 110, 99, 100])  # +10% then -10%
    spikes = find_spike_dates(closes, threshold=0.05, direction="both")
    assert len(spikes) == 2


# ---------------------------------------------------------------------------
# forward_cum_returns
# ---------------------------------------------------------------------------


def test_forward_cum_returns_single_event() -> None:
    # Event at index 1 (close 110). +2 horizon → close at index 3.
    closes = _closes([100, 110, 121, 133.1])
    fwd = forward_cum_returns(closes, [closes.index[1]], horizon=2)
    # 133.1 / 110 - 1 = 0.21
    assert len(fwd) == 1
    assert fwd[0] == pytest.approx(0.21, abs=1e-9)


def test_forward_cum_returns_drops_events_without_full_horizon() -> None:
    closes = _closes([100, 110, 121])
    # Event at last index has no +2 forward bar → dropped.
    fwd = forward_cum_returns(closes, [closes.index[2]], horizon=2)
    assert fwd == []


def test_forward_cum_returns_negative_after_spike() -> None:
    # Spike up to 120 at index 1, then reverts to 108 by index 3.
    closes = _closes([100, 120, 114, 108])
    fwd = forward_cum_returns(closes, [closes.index[1]], horizon=2)
    # 108 / 120 - 1 = -0.10 — buying the spike loses.
    assert fwd[0] == pytest.approx(-0.10, abs=1e-9)


# ---------------------------------------------------------------------------
# summarize_forward
# ---------------------------------------------------------------------------


def test_summarize_forward_basic_stats() -> None:
    s = summarize_forward([0.1, -0.05, 0.0, 0.2, -0.1])
    assert s["n"] == 5
    assert s["mean"] == pytest.approx((0.1 - 0.05 + 0.0 + 0.2 - 0.1) / 5)
    assert s["median"] == pytest.approx(0.0)
    # win_rate = fraction strictly positive = 2/5
    assert s["win_rate"] == pytest.approx(0.4)


def test_summarize_forward_empty() -> None:
    s = summarize_forward([])
    assert s["n"] == 0
    assert s["mean"] == 0.0
    assert s["win_rate"] == 0.0
