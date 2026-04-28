"""Tests for `bloasis.scoring.indicators` (TA-Lib wrappers)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from bloasis.scoring import indicators


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


def test_rsi_returns_nan_when_too_short() -> None:
    assert math.isnan(indicators.rsi_14(_series([1.0, 2.0, 3.0])))


def test_rsi_returns_value_for_sufficient_window() -> None:
    rng = np.random.default_rng(42)
    close = _series(list(100 + rng.standard_normal(50).cumsum()))
    v = indicators.rsi_14(close)
    assert 0.0 <= v <= 100.0


def test_macd_returns_triple_nan_when_too_short() -> None:
    m, s, h = indicators.macd(_series([1.0] * 10))
    assert math.isnan(m) and math.isnan(s) and math.isnan(h)


def test_macd_returns_finite_for_long_window() -> None:
    rng = np.random.default_rng(0)
    close = _series(list(100 + rng.standard_normal(80).cumsum()))
    m, s, h = indicators.macd(close)
    assert math.isfinite(m)
    assert math.isfinite(s)
    assert math.isfinite(h)


def test_adx_atr_short_window_nan() -> None:
    s = _series([1.0] * 5)
    assert math.isnan(indicators.adx_14(s, s, s))
    assert math.isnan(indicators.atr_14(s, s, s))


def test_adx_atr_finite_for_long_window() -> None:
    rng = np.random.default_rng(0)
    close = _series(list(100 + rng.standard_normal(60).cumsum()))
    high = close + 0.5
    low = close - 0.5
    assert math.isfinite(indicators.adx_14(high, low, close))
    assert math.isfinite(indicators.atr_14(high, low, close))


def test_bb_width_returns_value() -> None:
    rng = np.random.default_rng(7)
    close = _series(list(100 + rng.standard_normal(40).cumsum()))
    w = indicators.bb_width(close)
    assert math.isfinite(w)
    assert w > 0


def test_bb_width_short_window_nan() -> None:
    assert math.isnan(indicators.bb_width(_series([1.0] * 5)))


def test_sma_200_short_window_nan() -> None:
    assert math.isnan(indicators.sma(_series([1.0] * 100), period=200))


def test_sma_200_value_matches_mean() -> None:
    close = _series([float(i) for i in range(1, 201)])
    expected = float(sum(range(1, 201)) / 200)
    actual = indicators.sma(close, period=200)
    assert actual == pytest.approx(expected, rel=1e-6)
