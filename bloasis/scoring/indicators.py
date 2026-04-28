"""TA-Lib wrappers — RSI, MACD, ADX, ATR, Bollinger Bands.

Each function returns the *latest* indicator value (or NaN if the OHLCV
window is too short for the lookback). Callers always pass an
already-time-sliced DataFrame; we never look ahead inside this module.

Why "latest only" rather than the full series:
- Feature extraction operates per (symbol, timestamp) pair.
- Storing full indicator series everywhere bloats memory and risks
  accidentally feeding future data into a past-time feature.
- For backtest performance, callers can vectorize by fetching the full
  DataFrame and slicing — but the public API remains scalar-on-bar.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import talib

if TYPE_CHECKING:
    import pandas as pd

# Minimum bar counts before each indicator is meaningful. Below this we
# return NaN rather than risking divide-by-zero / startup transient noise.
MIN_BARS = {
    "rsi_14": 15,  # 14 + 1 to absorb the "previous" bar
    "macd": 35,  # 26-period EMA needs warmup
    "adx_14": 28,  # 2x lookback for true strength
    "atr_14": 15,
    "bb_width": 21,
    "sma_200": 200,
}


def _last_or_nan(arr: np.ndarray) -> float:
    """Return the last numeric value or NaN if the array is empty/all-nan."""
    if arr.size == 0:
        return float("nan")
    v = arr[-1]
    if isinstance(v, float) and math.isnan(v):
        return float("nan")
    if np.isnan(v):
        return float("nan")
    return float(v)


def rsi_14(close: pd.Series) -> float:
    if len(close) < MIN_BARS["rsi_14"]:
        return float("nan")
    return _last_or_nan(talib.RSI(close.to_numpy(dtype=np.float64), timeperiod=14))


def macd(close: pd.Series) -> tuple[float, float, float]:
    """Return (macd, signal, hist) at the last bar."""
    if len(close) < MIN_BARS["macd"]:
        nan = float("nan")
        return (nan, nan, nan)
    arr = close.to_numpy(dtype=np.float64)
    m, s, h = talib.MACD(arr, fastperiod=12, slowperiod=26, signalperiod=9)
    return (_last_or_nan(m), _last_or_nan(s), _last_or_nan(h))


def adx_14(high: pd.Series, low: pd.Series, close: pd.Series) -> float:
    if len(close) < MIN_BARS["adx_14"]:
        return float("nan")
    return _last_or_nan(
        talib.ADX(
            high.to_numpy(dtype=np.float64),
            low.to_numpy(dtype=np.float64),
            close.to_numpy(dtype=np.float64),
            timeperiod=14,
        )
    )


def atr_14(high: pd.Series, low: pd.Series, close: pd.Series) -> float:
    if len(close) < MIN_BARS["atr_14"]:
        return float("nan")
    return _last_or_nan(
        talib.ATR(
            high.to_numpy(dtype=np.float64),
            low.to_numpy(dtype=np.float64),
            close.to_numpy(dtype=np.float64),
            timeperiod=14,
        )
    )


def bb_width(close: pd.Series, period: int = 20) -> float:
    """Bollinger band width = (upper - lower) / middle."""
    if len(close) < period + 1:
        return float("nan")
    arr = close.to_numpy(dtype=np.float64)
    upper, middle, lower = talib.BBANDS(arr, timeperiod=period, nbdevup=2, nbdevdn=2)
    u = _last_or_nan(upper)
    m = _last_or_nan(middle)
    lo = _last_or_nan(lower)
    if math.isnan(u) or math.isnan(m) or math.isnan(lo) or m == 0.0:
        return float("nan")
    return (u - lo) / m


def sma(values: pd.Series, period: int) -> float:
    if len(values) < period:
        return float("nan")
    return _last_or_nan(talib.SMA(values.to_numpy(dtype=np.float64), timeperiod=period))
