"""Tests for `bloasis.scoring.extractor` — including the look-ahead regression.

The look-ahead regression is the most important test in the entire scoring
layer. If `ExtractionContext` ever stops asserting on future data, every
backtest result becomes statistically suspect (L007).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from bloasis.scoring.extractor import ExtractionContext, FeatureExtractor


def _ohlcv(n: int = 100, *, start: str = "2024-01-01") -> pd.DataFrame:
    """Synthetic OHLCV with mild trend + noise."""
    rng = np.random.default_rng(42)
    idx = pd.date_range(start, periods=n, freq="D")
    close = 100 + rng.standard_normal(n).cumsum() * 0.5
    high = close + 0.5
    low = close - 0.5
    open_ = close - 0.1
    volume = 1_000_000 + rng.integers(-50_000, 50_000, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


# ---------------------------------------------------------------------------
# Look-ahead regression — the cornerstone test (L007)
# ---------------------------------------------------------------------------


def test_evil_context_with_future_ohlcv_rejected() -> None:
    """Constructing a context whose ohlcv extends beyond timestamp must fail.

    This is the regression test for look-ahead bias. If the assertion is
    ever loosened, EVERY backtest result becomes suspect.
    """
    df = _ohlcv(50, start="2024-01-01")
    timestamp = datetime(2024, 1, 10, tzinfo=UTC)  # before df.max() = 2024-02-19

    with pytest.raises(ValueError, match="look-ahead"):
        ExtractionContext(
            timestamp=timestamp,
            symbol="EVIL",
            feature_version=1,
            sector="Technology",
            ohlcv=df,
        )


def test_evil_context_with_future_vix_rejected() -> None:
    df = _ohlcv(60)
    timestamp_naive = datetime(2024, 1, 10)  # match df's naive index for slicing
    timestamp = datetime(2024, 1, 10, tzinfo=UTC)
    vix = pd.Series(
        [20.0] * 60,
        index=pd.date_range("2024-01-01", periods=60, freq="D"),
    )
    # Slice df to be valid up to timestamp (using naive form to match index)
    df_sliced = df.loc[:timestamp_naive]

    with pytest.raises(ValueError, match="look-ahead in vix_series"):
        ExtractionContext(
            timestamp=timestamp,
            symbol="X",
            feature_version=1,
            sector=None,
            ohlcv=df_sliced,
            vix_series=vix,
        )


def test_evil_context_with_future_spy_rejected() -> None:
    df = _ohlcv(60)
    timestamp_naive = datetime(2024, 1, 10)
    timestamp = datetime(2024, 1, 10, tzinfo=UTC)
    df_sliced = df.loc[:timestamp_naive]
    spy = pd.Series(
        [400.0] * 60,
        index=pd.date_range("2024-01-01", periods=60, freq="D"),
    )

    with pytest.raises(ValueError, match="look-ahead in spy_close_series"):
        ExtractionContext(
            timestamp=timestamp,
            symbol="X",
            feature_version=1,
            sector=None,
            ohlcv=df_sliced,
            spy_close_series=spy,
        )


def test_clean_context_with_proper_slice_succeeds() -> None:
    df = _ohlcv(60)
    timestamp = df.index[-1].to_pydatetime().replace(tzinfo=UTC)
    ctx = ExtractionContext(
        timestamp=timestamp,
        symbol="OK",
        feature_version=1,
        sector="Technology",
        ohlcv=df,
    )
    assert ctx.symbol == "OK"


def test_empty_ohlcv_rejected() -> None:
    with pytest.raises(ValueError, match="empty ohlcv"):
        ExtractionContext(
            timestamp=datetime.now(tz=UTC),
            symbol="X",
            feature_version=1,
            sector=None,
            ohlcv=pd.DataFrame(),
        )


# ---------------------------------------------------------------------------
# FeatureExtractor.extract — happy path + missing fundamentals
# ---------------------------------------------------------------------------


def test_extract_populates_technicals() -> None:
    df = _ohlcv(80)
    timestamp = df.index[-1].to_pydatetime().replace(tzinfo=UTC)
    ctx = ExtractionContext(
        timestamp=timestamp,
        symbol="AAPL",
        feature_version=1,
        sector="Technology",
        ohlcv=df,
    )
    fv = FeatureExtractor().extract(ctx)
    assert fv.symbol == "AAPL"
    assert fv.sector == "Technology"
    assert math.isfinite(fv.rsi_14)
    assert math.isfinite(fv.macd)
    assert math.isfinite(fv.adx_14)
    assert math.isfinite(fv.atr_14)
    assert math.isfinite(fv.momentum_20d)
    assert math.isfinite(fv.volatility_20d)
    assert math.isfinite(fv.volume_ratio_20d)


def test_extract_short_window_yields_nan_technicals() -> None:
    df = _ohlcv(10)  # too short for RSI/MACD/etc
    timestamp = df.index[-1].to_pydatetime().replace(tzinfo=UTC)
    ctx = ExtractionContext(
        timestamp=timestamp,
        symbol="X",
        feature_version=1,
        sector=None,
        ohlcv=df,
    )
    fv = FeatureExtractor().extract(ctx)
    assert math.isnan(fv.rsi_14)
    assert math.isnan(fv.macd)
    assert math.isnan(fv.momentum_20d)


def test_extract_missing_fundamentals_become_nan() -> None:
    df = _ohlcv(40)
    timestamp = df.index[-1].to_pydatetime().replace(tzinfo=UTC)
    ctx = ExtractionContext(
        timestamp=timestamp,
        symbol="X",
        feature_version=1,
        sector=None,
        ohlcv=df,
        fundamentals={"per": 15.0, "roe": None},  # mixed
    )
    fv = FeatureExtractor().extract(ctx)
    assert fv.per == 15.0
    assert math.isnan(fv.roe)
    assert math.isnan(fv.pbr)


def test_extract_with_market_context_computes_vix_and_spy_above() -> None:
    df = _ohlcv(220)
    timestamp = df.index[-1].to_pydatetime().replace(tzinfo=UTC)
    vix = pd.Series([20.0] * 220, index=df.index)
    spy = pd.Series(np.linspace(300.0, 450.0, 220), index=df.index)
    ctx = ExtractionContext(
        timestamp=timestamp,
        symbol="X",
        feature_version=1,
        sector=None,
        ohlcv=df,
        vix_series=vix,
        spy_close_series=spy,
    )
    fv = FeatureExtractor().extract(ctx)
    assert fv.vix == 20.0
    assert fv.spy_above_sma200 == 1.0  # rising series → last > SMA200


def test_extract_with_sentiment_inputs() -> None:
    df = _ohlcv(40)
    timestamp = df.index[-1].to_pydatetime().replace(tzinfo=UTC)
    ctx = ExtractionContext(
        timestamp=timestamp,
        symbol="X",
        feature_version=1,
        sector=None,
        ohlcv=df,
        sentiment_score=0.4,
        news_count=8,
    )
    fv = FeatureExtractor().extract(ctx)
    assert fv.sentiment_score == 0.4
    assert fv.news_count == 8.0


def test_extract_version_mismatch_raises() -> None:
    df = _ohlcv(40)
    timestamp = df.index[-1].to_pydatetime().replace(tzinfo=UTC)
    ctx = ExtractionContext(
        timestamp=timestamp,
        symbol="X",
        feature_version=99,
        sector=None,
        ohlcv=df,
    )
    with pytest.raises(ValueError, match="feature_version mismatch"):
        FeatureExtractor().extract(ctx)
