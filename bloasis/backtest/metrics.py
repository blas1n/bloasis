"""Backtest performance metrics.

All inputs are pandas Series of equity values indexed by trading days.
Outputs are scalar floats. Annualization uses 252 trading days/year.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def daily_returns(equity: pd.Series) -> pd.Series:
    """Convert an equity curve to a daily simple return series.

    First day's return is dropped because there's no prior value to
    compare against.
    """
    return equity.pct_change().dropna()


def total_return(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def annualized_return(equity: pd.Series) -> float:
    if equity.empty or len(equity) < 2:
        return 0.0
    n_days = len(equity)
    growth = float(equity.iloc[-1] / equity.iloc[0])
    if growth <= 0:
        return -1.0
    years = n_days / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return 0.0
    return float(growth ** (1.0 / years) - 1.0)


def sharpe_ratio(equity: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe. risk_free_rate is annual; converted to daily."""
    rets = daily_returns(equity)
    if rets.empty or rets.std(ddof=1) == 0 or math.isnan(rets.std(ddof=1)):
        return 0.0
    daily_rf = (1.0 + risk_free_rate) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
    excess = rets - daily_rf
    return float(excess.mean() / excess.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(equity: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sortino — downside deviation only."""
    rets = daily_returns(equity)
    if rets.empty:
        return 0.0
    daily_rf = (1.0 + risk_free_rate) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
    excess = rets - daily_rf
    downside = excess[excess < 0]
    if downside.empty:
        return float("inf") if excess.mean() > 0 else 0.0
    downside_std = float(downside.std(ddof=1))
    if downside_std == 0 or math.isnan(downside_std):
        return 0.0
    return float(excess.mean() / downside_std * math.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough drawdown as a negative fraction."""
    if equity.empty:
        return 0.0
    cummax = equity.cummax()
    drawdowns = equity / cummax - 1.0
    return float(drawdowns.min())


def alpha_annualized(
    equity: pd.Series,
    benchmark: pd.Series,
) -> float:
    """Annualized alpha = annualized(strategy) - annualized(benchmark).

    Simple difference, not CAPM regression alpha — appropriate for our
    M2 / M1 mission language ("X% above SPY").
    """
    return annualized_return(equity) - annualized_return(benchmark)


def information_ratio(
    equity: pd.Series,
    benchmark: pd.Series,
) -> float:
    """Annualized IR — alpha divided by tracking error std dev."""
    er = daily_returns(equity)
    br = daily_returns(benchmark)
    aligned = er.align(br, join="inner")
    er_a, br_a = aligned[0], aligned[1]
    if er_a.empty:
        return 0.0
    diff = er_a - br_a
    sd = float(diff.std(ddof=1))
    if sd == 0 or math.isnan(sd):
        return 0.0
    return float(diff.mean() / sd * math.sqrt(TRADING_DAYS_PER_YEAR))


def months_beating_benchmark(
    equity: pd.Series,
    benchmark: pd.Series,
) -> tuple[int, int]:
    """Return (months strategy outperformed, total months observed).

    Used for the 'consistency vs SPY' metric in the M2 mission. Both
    series resampled to month-end and compared on simple period returns.
    """
    aligned = equity.align(benchmark, join="inner")
    e_a, b_a = aligned[0], aligned[1]
    if e_a.empty:
        return (0, 0)
    e_monthly = e_a.resample("ME").last().pct_change().dropna()
    b_monthly = b_a.resample("ME").last().pct_change().dropna()
    aligned_monthly = e_monthly.align(b_monthly, join="inner")
    em, bm = aligned_monthly[0], aligned_monthly[1]
    return (int((em > bm).sum()), int(len(em)))


def compute_metrics(
    equity: pd.Series,
    benchmark: pd.Series,
) -> dict[str, float]:
    """Bundle the common headline metrics into a dict for reporting."""
    return {
        "total_return": total_return(equity),
        "spy_total_return": total_return(benchmark),
        "annualized_return": annualized_return(equity),
        "annualized_alpha": alpha_annualized(equity, benchmark),
        "sharpe": sharpe_ratio(equity),
        "spy_sharpe": sharpe_ratio(benchmark),
        "sortino": sortino_ratio(equity),
        "max_drawdown": max_drawdown(equity),
        "spy_max_drawdown": max_drawdown(benchmark),
        "information_ratio": information_ratio(equity, benchmark),
    }


def safe_ratio(numerator: float, denominator: float) -> float:
    """`numerator / denominator`, returning 0.0 when denominator is ~0."""
    if abs(denominator) < 1e-12 or math.isnan(denominator):
        return 0.0
    if not np.isfinite(numerator) or not np.isfinite(denominator):
        return 0.0
    return float(numerator / denominator)
