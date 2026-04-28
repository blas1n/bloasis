"""Tests for `bloasis.scoring.derived`."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from bloasis.scoring.derived import (
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
