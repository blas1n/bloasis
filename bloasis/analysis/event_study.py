"""Event-study primitives — pure compute, no I/O (PR54).

Two studies built on the same `forward_cum_returns` core:

  post-spike reversion — find days with a big single-day move, then
    measure forward cumulative return over N days. Generalizes the
    "buy the earnings-call news spike, watch it fall" case: if the
    average forward return after up-spikes is negative, chasing spikes
    is a losing game (mean reversion dominates the late-arriving buyer).

  hub-earnings drift — feed a related stock's closes + a hub's earnings
    dates as events; measures whether the linked name drifts after the
    hub reports (Cohen-Frazzini economic-link lag).
"""

from __future__ import annotations

import statistics
from typing import Literal

import pandas as pd


def daily_returns(closes: pd.Series) -> pd.Series:
    """1-day pct returns, NaN row dropped."""
    return closes.pct_change().dropna()


def find_spike_dates(
    closes: pd.Series,
    threshold: float,
    direction: Literal["up", "down", "both"] = "up",
) -> list[pd.Timestamp]:
    """Dates whose 1-day return crosses ``threshold`` in ``direction``.

    threshold is a positive fraction (0.05 = 5%). For ``down`` a return
    <= -threshold qualifies; for ``both`` either side.
    """
    rets = daily_returns(closes)
    if direction == "up":
        mask = rets >= threshold
    elif direction == "down":
        mask = rets <= -threshold
    else:
        mask = rets.abs() >= threshold
    return list(rets.index[mask])


def forward_cum_returns(
    closes: pd.Series,
    event_dates: list[pd.Timestamp],
    horizon: int,
) -> list[float]:
    """Cumulative return from each event date's close to +``horizon`` bars.

    For an event at position i (close C_i), the forward return is
    C_{i+horizon} / C_i - 1. Events without a full horizon of forward
    bars are dropped (can't measure what hasn't happened).
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    out: list[float] = []
    index = closes.index
    pos_of = {ts: i for i, ts in enumerate(index)}
    for ev in event_dates:
        i = pos_of.get(ev)
        if i is None or i + horizon >= len(index):
            continue
        c0 = float(closes.iloc[i])
        c1 = float(closes.iloc[i + horizon])
        if c0 > 0:
            out.append(c1 / c0 - 1.0)
    return out


def summarize_forward(values: list[float]) -> dict[str, float]:
    """mean / median / win_rate (fraction strictly positive) / n."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": 0.0, "median": 0.0, "win_rate": 0.0}
    wins = sum(1 for v in values if v > 0)
    return {
        "n": n,
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "win_rate": wins / n,
    }
