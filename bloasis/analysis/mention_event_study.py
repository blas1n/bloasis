"""Decompose a mention's price impact into gap / intraday / forward (PR55).

The gap insight from the user — out-of-hours news compresses its whole
reaction into the next session's opening gap, which retail can't trade
because the OPEN print already incorporates pre-market activity. Only
the post-open move is retail-feasible. This module makes that explicit.

Given a daily OHLC panel and an event entry date T:

  gap      = open[T] / close[T-1] − 1     (HFT/pre-market captured)
  intraday = close[T] / open[T] − 1       (T's session, post-open)
  forward  = close[T+h] / open[T] − 1     (open→T+h close, retail horizon)
  total    = close[T+h] / close[T-1] − 1  (the full pre-to-post move)

Aggregated:
  gap_fraction = mean_gap / mean_total — how much of the total event
    move was already in the open. A value near 1 means HFT got it
    all; near 0 means the move played out post-open (retail-feasible).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

EventRow = dict[str, float]


def decompose_event_return(
    bars: pd.DataFrame, *, entry_date: date, horizon: int
) -> EventRow | None:
    """Return gap/intraday/forward/total for an event at ``entry_date``.

    Requires:
      - entry_date is a trading bar in ``bars.index`` (Saturday/holiday skipped)
      - a prior bar exists (for gap baseline = previous close)
      - at least ``horizon`` forward bars exist (for forward leg)

    Returns None when any of those preconditions miss.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    idx = pd.DatetimeIndex(bars.index)
    # locate entry_date — strip tz from index for date-only matching
    idx_naive = idx.tz_localize(None) if idx.tz is not None else idx
    entry_ts = pd.Timestamp(entry_date.isoformat())
    if entry_ts not in idx_naive:
        return None
    loc = idx_naive.get_loc(entry_ts)
    if not isinstance(loc, int):  # mask or slice from duplicates — bail
        return None
    pos = loc
    if pos == 0:
        return None  # no previous close → no gap anchor
    if pos + horizon >= len(idx):
        return None  # not enough forward bars

    prev_close = float(bars.iloc[pos - 1]["close"])
    open_t = float(bars.iloc[pos]["open"])
    close_t = float(bars.iloc[pos]["close"])
    close_th = float(bars.iloc[pos + horizon]["close"])
    if prev_close <= 0 or open_t <= 0:
        return None

    return {
        "gap": open_t / prev_close - 1.0,
        "intraday": close_t / open_t - 1.0,
        "forward": close_th / open_t - 1.0,
        "total": close_th / prev_close - 1.0,
    }


def summarize_decomposed(rows: list[EventRow]) -> dict[str, float]:
    """Aggregate per-event decompositions.

    ``gap_fraction`` answers the retail question: what share of the
    average event total move was the opening gap? Approaches 1 = HFT
    captured everything; approaches 0 = move played out post-open.
    """
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "mean_gap": 0.0,
            "mean_intraday": 0.0,
            "mean_forward": 0.0,
            "mean_total": 0.0,
            "gap_fraction": 0.0,
        }
    mean_gap = sum(r["gap"] for r in rows) / n
    mean_intraday = sum(r["intraday"] for r in rows) / n
    mean_forward = sum(r["forward"] for r in rows) / n
    mean_total = sum(r["total"] for r in rows) / n
    gap_fraction = mean_gap / mean_total if mean_total != 0 else 0.0
    return {
        "n": n,
        "mean_gap": mean_gap,
        "mean_intraday": mean_intraday,
        "mean_forward": mean_forward,
        "mean_total": mean_total,
        "gap_fraction": gap_fraction,
    }
