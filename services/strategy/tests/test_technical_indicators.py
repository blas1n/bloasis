"""Unit tests for Technical Indicators (TA-Lib wrapper)."""

import numpy as np

from src.technical_indicators import (
    TechnicalIndicators,
    calculate_indicators,
    format_indicators_summary,
)


def _make_bars(n: int, base: float = 100.0, trend: float = 0.5) -> list[dict]:
    """Generate synthetic OHLCV bars with controllable trend.

    Args:
        n: Number of bars.
        base: Starting close price.
        trend: Per-bar price increment.

    Returns:
        List of OHLCV dicts.
    """
    bars = []
    for i in range(n):
        c = base + i * trend
        bars.append({
            "open": c - 0.5,
            "high": c + 1.0,
            "low": c - 1.0,
            "close": c,
            "volume": 1_000_000 + i * 10_000,
        })
    return bars


class TestCalculateIndicators:
    """Tests for calculate_indicators()."""

    def test_returns_none_for_insufficient_data(self):
        """Need at least 26 bars."""
        bars = _make_bars(25)
        result = calculate_indicators("TEST", bars)
        assert result is None

    def test_returns_indicators_for_sufficient_data(self):
        """26+ bars should produce valid indicators."""
        bars = _make_bars(60)
        ind = calculate_indicators("AAPL", bars)

        assert ind is not None
        assert isinstance(ind, TechnicalIndicators)
        assert ind.symbol == "AAPL"

    def test_rsi_in_valid_range(self):
        bars = _make_bars(60)
        ind = calculate_indicators("RSI", bars)
        assert 0 <= ind.rsi_14 <= 100

    def test_atr_positive(self):
        bars = _make_bars(60)
        ind = calculate_indicators("ATR", bars)
        assert ind.atr_14 > 0

    def test_macd_components_populated(self):
        bars = _make_bars(60)
        ind = calculate_indicators("MACD", bars)
        # MACD values should be finite numbers
        assert np.isfinite(ind.macd)
        assert np.isfinite(ind.macd_signal)
        assert np.isfinite(ind.macd_hist)

    def test_bollinger_bands_ordering(self):
        bars = _make_bars(60)
        ind = calculate_indicators("BB", bars)
        assert ind.bb_lower < ind.bb_mid < ind.bb_upper

    def test_moving_averages_positive(self):
        bars = _make_bars(60, base=100.0)
        ind = calculate_indicators("MA", bars)
        assert ind.sma_20 > 0
        assert ind.sma_50 > 0
        assert ind.ema_12 > 0
        assert ind.ema_26 > 0

    def test_stochastic_in_valid_range(self):
        bars = _make_bars(60)
        ind = calculate_indicators("STOCH", bars)
        assert 0 <= ind.stoch_k <= 100
        assert 0 <= ind.stoch_d <= 100

    def test_adx_in_valid_range(self):
        bars = _make_bars(60)
        ind = calculate_indicators("ADX", bars)
        assert 0 <= ind.adx <= 100

    def test_atr_series_populated(self):
        bars = _make_bars(60)
        ind = calculate_indicators("SERIES", bars)
        assert len(ind.atr_series) == 60  # Same length as input

    def test_obv_populated(self):
        bars = _make_bars(60)
        ind = calculate_indicators("OBV", bars)
        assert ind.obv != 0  # OBV should accumulate

    def test_uptrend_high_rsi(self):
        """Strong uptrend should produce elevated RSI."""
        bars = _make_bars(60, base=50.0, trend=2.0)
        ind = calculate_indicators("UP", bars)
        assert ind.rsi_14 > 60

    def test_downtrend_low_rsi(self):
        """Strong downtrend should produce depressed RSI."""
        bars = _make_bars(60, base=200.0, trend=-2.0)
        ind = calculate_indicators("DOWN", bars)
        assert ind.rsi_14 < 40


class TestFormatIndicatorsSummary:
    """Tests for format_indicators_summary()."""

    def test_format_contains_symbol(self):
        bars = _make_bars(60)
        ind = calculate_indicators("AAPL", bars)
        summary = format_indicators_summary(ind)
        assert "AAPL" in summary

    def test_format_contains_key_indicators(self):
        bars = _make_bars(60)
        ind = calculate_indicators("AAPL", bars)
        summary = format_indicators_summary(ind)
        assert "RSI=" in summary
        assert "MACD=" in summary
        assert "ATR=" in summary
        assert "BB=" in summary
        assert "SMA20=" in summary
        assert "SMA50=" in summary
        assert "Stoch=" in summary
        assert "OBV=" in summary

    def test_format_returns_string(self):
        bars = _make_bars(60)
        ind = calculate_indicators("AAPL", bars)
        summary = format_indicators_summary(ind)
        assert isinstance(summary, str)
        assert len(summary) > 0
