"""Tests for core/technical_indicators.py — TA-Lib calculations."""

import numpy as np

from app.core.technical_indicators import (
    TechnicalIndicators,
    calculate_indicators,
    format_indicators_summary,
)


def _make_bars(n: int = 60, base: float = 100.0, trend: float = 0.1) -> list[dict]:
    """Generate synthetic OHLCV bars with a trend."""
    bars = []
    for i in range(n):
        c = base + trend * i
        bars.append(
            {
                "open": c - 0.5,
                "high": c + 1.5,
                "low": c - 1.5,
                "close": c,
                "volume": 1_000_000 + i * 1000,
            }
        )
    return bars


class TestCalculateIndicators:
    def test_basic_calculation(self):
        bars = _make_bars(60)
        result = calculate_indicators("AAPL", bars)
        assert result is not None
        assert result.symbol == "AAPL"
        assert isinstance(result.rsi_14, float)
        assert isinstance(result.macd, float)
        assert isinstance(result.atr_14, float)
        assert isinstance(result.adx, float)
        assert isinstance(result.bb_upper, float)
        assert isinstance(result.bb_mid, float)
        assert isinstance(result.bb_lower, float)
        assert isinstance(result.sma_20, float)
        assert isinstance(result.sma_50, float)
        assert isinstance(result.ema_12, float)
        assert isinstance(result.ema_26, float)
        assert isinstance(result.stoch_k, float)
        assert isinstance(result.stoch_d, float)
        assert isinstance(result.obv, float)

    def test_returns_none_insufficient_data(self):
        bars = _make_bars(10)
        result = calculate_indicators("AAPL", bars)
        assert result is None

    def test_returns_none_with_25_bars(self):
        """Need at least 26 bars."""
        bars = _make_bars(25)
        result = calculate_indicators("AAPL", bars)
        assert result is None

    def test_returns_result_with_26_bars(self):
        """Minimum 26 bars should work."""
        bars = _make_bars(26)
        result = calculate_indicators("AAPL", bars)
        assert result is not None

    def test_empty_bars(self):
        result = calculate_indicators("AAPL", [])
        assert result is None

    def test_rsi_within_bounds(self):
        bars = _make_bars(60)
        result = calculate_indicators("AAPL", bars)
        assert result is not None
        assert 0 <= result.rsi_14 <= 100

    def test_bollinger_band_ordering(self):
        bars = _make_bars(60)
        result = calculate_indicators("AAPL", bars)
        assert result is not None
        assert result.bb_lower <= result.bb_mid <= result.bb_upper

    def test_atr_series_populated(self):
        bars = _make_bars(60)
        result = calculate_indicators("AAPL", bars)
        assert result is not None
        assert isinstance(result.atr_series, np.ndarray)
        assert len(result.atr_series) == 60

    def test_upward_trend_sma(self):
        """With strong upward trend, SMA20 should be above SMA50."""
        bars = _make_bars(100, base=50.0, trend=1.0)
        result = calculate_indicators("AAPL", bars)
        assert result is not None
        assert result.sma_20 > result.sma_50


class TestFormatIndicatorsSummary:
    def test_basic_format(self):
        indicators = TechnicalIndicators(
            symbol="AAPL",
            rsi_14=55.3,
            macd=1.25,
            macd_signal=0.80,
            macd_hist=0.45,
            adx=25.0,
            atr_14=3.50,
            bb_upper=155.0,
            bb_mid=150.0,
            bb_lower=145.0,
            sma_20=151.0,
            sma_50=148.0,
            stoch_k=65.0,
            stoch_d=60.0,
            obv=5_000_000.0,
        )
        summary = format_indicators_summary(indicators)
        assert "AAPL" in summary
        assert "RSI=55.3" in summary
        assert "MACD=1.25" in summary
        assert "ADX=25.0" in summary
        assert "ATR=3.50" in summary
        assert "SMA20=151.00" in summary
        assert "SMA50=148.00" in summary
        assert "Stoch=65.0/60.0" in summary
        assert "OBV=5,000,000" in summary

    def test_format_with_defaults(self):
        indicators = TechnicalIndicators(symbol="TEST")
        summary = format_indicators_summary(indicators)
        assert "TEST" in summary
        assert "RSI=50.0" in summary

    def test_format_with_calculated_indicators(self):
        bars = _make_bars(60)
        result = calculate_indicators("MSFT", bars)
        assert result is not None
        summary = format_indicators_summary(result)
        assert "MSFT" in summary
        assert "RSI=" in summary
        assert "MACD=" in summary
