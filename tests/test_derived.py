"""Tests for `bloasis.scoring.derived`."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from bloasis.scoring.derived import (
    corr_price_volume,
    kbar_kmid2,
    kbar_ksft2,
    momentum,
    vix_zscore_60d,
    volatility_annualized,
    volume_ratio,
)


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# momentum
# ---------------------------------------------------------------------------


def test_momentum_positive_run() -> None:
    close = _series([100.0] + [101 + i for i in range(20)])
    m = momentum(close, lookback=20)
    assert m == pytest.approx((120.0 - 100.0) / 100.0)


def test_momentum_short_window_nan() -> None:
    assert math.isnan(momentum(_series([1.0, 2.0]), lookback=20))


def test_momentum_zero_base_nan() -> None:
    close = _series([0.0] + [1.0] * 20)
    assert math.isnan(momentum(close, lookback=20))


def test_momentum_skip_jegadeesh_titman_12_1() -> None:
    """`skip=21` excludes the most recent 21 bars (12-1 momentum)."""
    # 30-bar series: index -29 (oldest) ... 0 (newest)
    # With lookback=5, skip=2: window is close[-8 .. -3], i.e. base=close[-8], top=close[-3]
    values = list(range(100, 130))  # 30 bars: 100, 101, ..., 129
    close = _series(values)
    m = momentum(close, lookback=5, skip=2)
    # base = close[-(5+2+1)] = close[-8] = 122; top = close[-(2+1)] = close[-3] = 127
    assert m == pytest.approx((127 - 122) / 122)


def test_momentum_skip_zero_matches_default() -> None:
    """`skip=0` should be identical to omitting `skip`."""
    close = _series([100.0] + [101 + i for i in range(20)])
    assert momentum(close, lookback=20, skip=0) == pytest.approx(momentum(close, lookback=20))


def test_momentum_skip_insufficient_history_nan() -> None:
    """Need at least lookback+skip+1 bars; otherwise NaN."""
    close = _series([100.0] * 10)
    assert math.isnan(momentum(close, lookback=5, skip=10))


# ---------------------------------------------------------------------------
# volatility
# ---------------------------------------------------------------------------


def test_volatility_constant_is_zero() -> None:
    close = _series([100.0] * 25)
    assert volatility_annualized(close) == 0.0


def test_volatility_finite_for_random() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    close = _series(list(100 + rng.standard_normal(30).cumsum()))
    v = volatility_annualized(close)
    assert math.isfinite(v)
    assert v > 0


def test_volatility_short_window_nan() -> None:
    assert math.isnan(volatility_annualized(_series([1.0, 2.0])))


def test_volatility_negative_price_nan() -> None:
    close = _series([1.0] * 10 + [-1.0] * 15)
    assert math.isnan(volatility_annualized(close))


# ---------------------------------------------------------------------------
# volume_ratio
# ---------------------------------------------------------------------------


def test_volume_ratio_one_when_constant() -> None:
    vol = _series([1000.0] * 25)
    assert volume_ratio(vol) == pytest.approx(1.0)


def test_volume_ratio_double() -> None:
    vol = _series([1000.0] * 20 + [2000.0])
    assert volume_ratio(vol) == pytest.approx(2.0)


def test_volume_ratio_zero_avg_nan() -> None:
    vol = _series([0.0] * 20 + [100.0])
    assert math.isnan(volume_ratio(vol))


def test_volume_ratio_short_window_nan() -> None:
    assert math.isnan(volume_ratio(_series([1.0, 2.0])))


# ---------------------------------------------------------------------------
# vix_zscore_60d
# ---------------------------------------------------------------------------


def test_vix_zscore_zero_when_constant() -> None:
    vix = _series([20.0] * 60)
    assert math.isnan(vix_zscore_60d(vix))  # std=0 case


def test_vix_zscore_positive_when_above_mean() -> None:
    vix = _series([20.0] * 59 + [40.0])
    z = vix_zscore_60d(vix)
    assert z > 0


def test_vix_zscore_short_series_nan() -> None:
    assert math.isnan(vix_zscore_60d(_series([15.0] * 30)))


# ---------------------------------------------------------------------------
# kbar_kmid2 — candlestick body normalized by range
# ---------------------------------------------------------------------------


def test_kbar_kmid2_white_candle_positive() -> None:
    """Close > Open in a wide range → KMID2 > 0."""
    o = _series([100.0])
    h = _series([105.0])
    low = _series([99.0])
    c = _series([104.0])
    # (104 - 100) / (105 - 99) = 4/6 = 0.6667
    assert kbar_kmid2(o, h, low, c) == pytest.approx(4.0 / 6.0)


def test_kbar_kmid2_black_candle_negative() -> None:
    o = _series([100.0])
    h = _series([101.0])
    low = _series([95.0])
    c = _series([96.0])
    assert kbar_kmid2(o, h, low, c) == pytest.approx(-4.0 / 6.0)


def test_kbar_kmid2_doji_zero_range_safe() -> None:
    """high == low (doji) → epsilon protects against div-by-zero, returns small finite."""
    o = _series([100.0])
    h = _series([100.0])
    low = _series([100.0])
    c = _series([100.0])
    v = kbar_kmid2(o, h, low, c)
    assert math.isfinite(v)
    assert v == pytest.approx(0.0)


def test_kbar_kmid2_uses_latest_bar_only() -> None:
    """KMID2 reads only the last bar — earlier bars don't affect the result."""
    o = _series([100.0, 200.0])
    h = _series([110.0, 205.0])
    low = _series([99.0, 199.0])
    c = _series([105.0, 204.0])
    # Only second bar: (204 - 200) / (205 - 199) = 4/6
    assert kbar_kmid2(o, h, low, c) == pytest.approx(4.0 / 6.0)


def test_kbar_kmid2_empty_nan() -> None:
    o = _series([])
    h = _series([])
    low = _series([])
    c = _series([])
    assert math.isnan(kbar_kmid2(o, h, low, c))


# ---------------------------------------------------------------------------
# kbar_ksft2 — close position within high-low range
# ---------------------------------------------------------------------------


def test_kbar_ksft2_close_at_high_positive() -> None:
    """Close at high → (2*close - high - low) / (high - low) = (high - low)/(high - low) = 1."""
    h = _series([110.0])
    low = _series([90.0])
    c = _series([110.0])
    assert kbar_ksft2(h, low, c) == pytest.approx(1.0)


def test_kbar_ksft2_close_at_low_negative_one() -> None:
    h = _series([110.0])
    low = _series([90.0])
    c = _series([90.0])
    assert kbar_ksft2(h, low, c) == pytest.approx(-1.0)


def test_kbar_ksft2_close_at_midpoint_zero() -> None:
    h = _series([110.0])
    low = _series([90.0])
    c = _series([100.0])
    assert kbar_ksft2(h, low, c) == pytest.approx(0.0)


def test_kbar_ksft2_doji_safe() -> None:
    h = _series([100.0])
    low = _series([100.0])
    c = _series([100.0])
    v = kbar_ksft2(h, low, c)
    assert math.isfinite(v)


def test_kbar_ksft2_uses_latest_bar_only() -> None:
    h = _series([200.0, 110.0])
    low = _series([100.0, 90.0])
    c = _series([150.0, 100.0])
    # Only last bar: (200 - 110 - 90) / (110 - 90) = 0/20 = 0
    assert kbar_ksft2(h, low, c) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# corr_price_volume — Pearson corr of pct returns vs log volume
# ---------------------------------------------------------------------------


def test_corr_pv_perfectly_aligned_positive() -> None:
    """Returns and log(volume) move together → positive correlation."""
    import numpy as np

    rng = np.random.default_rng(42)
    rets = rng.normal(0.0, 0.02, 25)
    close_vals = [100.0]
    for r in rets:
        close_vals.append(close_vals[-1] * (1.0 + r))
    # Volume tracks return sign + magnitude (high return ↔ high volume).
    vols = 1_000_000.0 * np.exp(rets * 5.0)
    close = _series(close_vals[1:])
    volume = _series(list(vols))
    c = corr_price_volume(close, volume, window=20)
    assert c > 0.5


def test_corr_pv_anti_correlated_negative() -> None:
    """Returns inversely related to volume → negative correlation."""
    import numpy as np

    rng = np.random.default_rng(7)
    rets = rng.normal(0.0, 0.02, 25)
    close_vals = [100.0]
    for r in rets:
        close_vals.append(close_vals[-1] * (1.0 + r))
    vols = 1_000_000.0 * np.exp(-rets * 5.0)  # inverse relationship
    close = _series(close_vals[1:])
    volume = _series(list(vols))
    c = corr_price_volume(close, volume, window=20)
    assert c < -0.5


def test_corr_pv_short_window_nan() -> None:
    close = _series([100.0, 101.0, 102.0])
    volume = _series([1000.0, 1100.0, 1200.0])
    assert math.isnan(corr_price_volume(close, volume, window=20))


def test_corr_pv_constant_returns_nan() -> None:
    """std=0 on returns → corr undefined → NaN."""
    close = _series([100.0] * 25)  # zero returns throughout
    volume = _series([1000.0 + i for i in range(25)])
    assert math.isnan(corr_price_volume(close, volume, window=20))


def test_corr_pv_zero_volume_safe() -> None:
    """log(0) protected — caller passes log1p or we add epsilon — must not crash."""
    close = _series([100.0 + i for i in range(25)])
    volume = _series([0.0] + [1000.0 + i for i in range(24)])
    v = corr_price_volume(close, volume, window=20)
    # Either finite (handled internally) or NaN (acceptable). Just must not raise.
    assert math.isfinite(v) or math.isnan(v)
