"""Price/volume-derived features that don't need TA-Lib.

These live separately from `indicators.py` so a TA-Lib-less environment
(e.g., feature analysis on a server without libta-lib) can still compute
momentum / volatility / volume_ratio if needed. Currently both modules
are imported from `extractor.py`, but the boundary is intentional.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def momentum(close: pd.Series, lookback: int, *, skip: int = 0) -> float:
    """Pct return over a `lookback`-bar window ending `skip` bars ago.

    `skip=0` reproduces the classic trailing return:
        (close[-1] - close[-lookback-1]) / close[-lookback-1]

    `skip>0` excludes the most recent `skip` bars — this is the
    Jegadeesh-Titman 1993 12-1 momentum convention (`lookback=252, skip=21`):
        base = close[-(lookback+skip+1)]
        top  = close[-(skip+1)]
        return (top - base) / base
    """
    if skip < 0:
        raise ValueError(f"skip must be >= 0, got {skip}")
    if len(close) < lookback + skip + 1:
        return float("nan")
    base = close.iloc[-(lookback + skip + 1)]
    top = close.iloc[-(skip + 1)]
    if base == 0 or (isinstance(base, float) and math.isnan(base)):
        return float("nan")
    return float((top - base) / base)


def volatility_annualized(close: pd.Series, window: int = 20) -> float:
    """Annualized standard deviation of daily log returns over `window` bars."""
    if len(close) < window + 1:
        return float("nan")
    arr = close.to_numpy(dtype=np.float64)[-window - 1 :]
    if (arr <= 0).any():
        return float("nan")
    log_returns = np.diff(np.log(arr))
    if log_returns.size == 0:
        return float("nan")
    sd = float(np.std(log_returns, ddof=1))
    return sd * math.sqrt(TRADING_DAYS_PER_YEAR)


def volume_ratio(volume: pd.Series, window: int = 20) -> float:
    """Today's volume / `window`-bar average volume."""
    if len(volume) < window + 1:
        return float("nan")
    arr = volume.to_numpy(dtype=np.float64)
    today = arr[-1]
    avg = arr[-window - 1 : -1].mean()
    if avg == 0 or math.isnan(avg):
        return float("nan")
    return float(today / avg)


def vix_zscore_60d(vix_series: pd.Series) -> float:
    """60-day z-score of VIX: (VIX_today - mean_60d) / std_60d.

    Returns NaN when the series is too short or std is zero.
    """
    window = 60
    if len(vix_series) < window:
        return float("nan")
    arr = vix_series.to_numpy(dtype=np.float64)[-window:]
    today = arr[-1]
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    if std == 0 or math.isnan(std):
        return float("nan")
    return float((today - mean) / std)
