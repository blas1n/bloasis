"""Build a monthly-rebalanced universe map for the backtest engine.

Wires `bloasis.data.universe.list_sp500_at` into `BacktestData.universe_by_date`.
For each calendar month start in [start, end], record that month's S&P 500
membership. Engine's `BacktestData.universe_at(d)` then picks the most
recent rebalance entry — implementing L001 (survivorship bias) mitigation.

Daily rebalance was rejected: index membership rarely changes intraday,
and monthly granularity matches the fja05680 dataset's update cadence.
"""

from __future__ import annotations

import contextlib
from datetime import date
from pathlib import Path

from bloasis.data.universe.sp500_historical import list_sp500_at


def build_monthly_universe(
    start: date,
    end: date,
    *,
    cache_dir: Path,
) -> dict[date, list[str]]:
    """Return `{first_day_of_month: [symbols]}` covering [start, end].

    The first entry is the rebalance for `start`'s month — even if `start`
    is mid-month — so the engine has membership info for day 1.
    """
    if start >= end:
        raise ValueError(f"start ({start}) must be < end ({end})")

    out: dict[date, list[str]] = {}
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        # `cursor` predates the dataset — skip and let caller handle.
        with contextlib.suppress(ValueError):
            out[cursor] = list_sp500_at(cursor, cache_dir=cache_dir)
        cursor = _next_month_first(cursor)
    return out


def _next_month_first(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def latest_membership_at(
    universe_map: dict[date, list[str]],
    as_of: date,
) -> list[str]:
    """Pick the most recent rebalance entry with date <= as_of."""
    eligible = [k for k in universe_map if k <= as_of]
    if not eligible:
        return []
    return universe_map[max(eligible)]


__all__ = ["build_monthly_universe", "latest_membership_at"]
