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


def residual_momentum(
    close: pd.Series,
    market_close: pd.Series,
    *,
    lookback: int = 252,
    skip: int = 21,
) -> float:
    """Blitz-Hanauer-Vidojevic 2020 idiosyncratic momentum.

    Same JT 12-1 window (`lookback=252, skip=21`), but on
    market-beta-residualized daily returns:

        s_ret = α + β · m_ret + ε
        residual_momentum = sum(ε over [-(lookback+skip+1) : -(skip+1)])

    Lower vol than raw momentum, no return drop. Drop-in fix for vanilla
    JT's drawdown failure (1.46 in our 2022-2024 SP500 measurement).

    Returns NaN if either series is too short or the regression denominator
    (variance of market returns) is zero.
    """
    import pandas as pd

    if len(close) < lookback + skip + 2:
        return float("nan")
    if len(market_close) < lookback + skip + 2:
        return float("nan")

    aligned = pd.concat(
        [close.rename("s"), market_close.rename("m")], axis=1, join="inner"
    ).dropna()
    if len(aligned) < lookback + skip + 2:
        return float("nan")
    aligned = aligned.iloc[-(lookback + skip + 1) :]

    s_ret = aligned["s"].pct_change().dropna().to_numpy(dtype=np.float64)
    m_ret = aligned["m"].pct_change().dropna().to_numpy(dtype=np.float64)
    n = min(len(s_ret), len(m_ret))
    if n < skip + 5:
        return float("nan")
    s_ret, m_ret = s_ret[-n:], m_ret[-n:]

    var_m = float(np.var(m_ret, ddof=1))
    if var_m == 0:
        return float("nan")
    cov_sm = float(np.cov(s_ret, m_ret, ddof=1)[0, 1])
    beta = cov_sm / var_m
    residuals = s_ret - beta * m_ret

    # Drop the trailing `skip` days (J-T mean-reversion lag)
    drift = residuals[:-skip] if skip > 0 else residuals
    if drift.size == 0:
        return float("nan")
    return float(drift.sum())


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


# ---------------------------------------------------------------------------
# qlib-derived microstructure / interaction features (PR12)
# ---------------------------------------------------------------------------

_KBAR_EPS = 1e-12


def kbar_kmid2(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> float:
    """Candlestick body normalized by the bar's range (qlib KMID2).

        (close - open) / (high - low + eps)

    Operates on the latest bar only. Positive = white candle, negative = black.
    """
    if len(close) == 0:
        return float("nan")
    o = float(open_.iloc[-1])
    h = float(high.iloc[-1])
    low_ = float(low.iloc[-1])
    c = float(close.iloc[-1])
    rng = (h - low_) + _KBAR_EPS
    if rng <= 0:
        return float("nan")
    return float((c - o) / rng)


def kbar_ksft2(high: pd.Series, low: pd.Series, close: pd.Series) -> float:
    """Close position within the bar's range, mapped to [-1, 1] (qlib KSFT2).

        (2*close - high - low) / (high - low + eps)

    +1 = close at high, -1 = close at low, 0 = midpoint. Latest bar only.
    """
    if len(close) == 0:
        return float("nan")
    h = float(high.iloc[-1])
    low_ = float(low.iloc[-1])
    c = float(close.iloc[-1])
    rng = (h - low_) + _KBAR_EPS
    if rng <= 0:
        return float("nan")
    return float((2 * c - h - low_) / rng)


def corr_price_volume(close: pd.Series, volume: pd.Series, window: int = 20) -> float:
    """Pearson correlation of pct returns vs log(1+volume) over `window` bars.

    Llorente et al. 2002: positive corr → informed trading dominates,
    negative → noise/liquidity-driven (mean reversion likely). NaN if std=0.
    """
    if len(close) < window + 1 or len(volume) < window + 1:
        return float("nan")
    c_arr = close.to_numpy(dtype=np.float64)[-window - 1 :]
    v_arr = volume.to_numpy(dtype=np.float64)[-window:]
    if (c_arr <= 0).any():
        return float("nan")
    rets = np.diff(c_arr) / c_arr[:-1]
    log_vol = np.log1p(np.maximum(v_arr, 0.0))
    if rets.size != log_vol.size:
        return float("nan")
    if float(np.std(rets, ddof=1)) == 0 or float(np.std(log_vol, ddof=1)) == 0:
        return float("nan")
    coef = float(np.corrcoef(rets, log_vol)[0, 1])
    if math.isnan(coef):
        return float("nan")
    return coef
