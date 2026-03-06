"""Tests for core/factor_scoring.py — no mocks needed."""

from decimal import Decimal

import pytest

from app.core.factor_scoring import (
    calculate_final_score,
    calculate_liquidity,
    calculate_momentum,
    calculate_quality,
    calculate_sentiment_from_momentum,
    calculate_value,
    calculate_volatility,
)
from app.core.models import FactorScores


def _make_bars(n: int = 60, base_close: float = 100.0, trend: float = 0.0) -> list[dict]:
    """Generate synthetic OHLCV bars."""
    bars = []
    for i in range(n):
        c = base_close + trend * i
        bars.append(
            {
                "open": c - 0.5,
                "high": c + 1.0,
                "low": c - 1.0,
                "close": c,
                "volume": 1_500_000,
            }
        )
    return bars


class TestMomentum:
    def test_above_ma20(self):
        # Price trending up — close should be above MA20
        bars = _make_bars(30, base_close=100, trend=0.5)
        score = calculate_momentum(bars)
        assert score > 50

    def test_below_ma20(self):
        # Price trending down
        bars = _make_bars(30, base_close=110, trend=-0.5)
        score = calculate_momentum(bars)
        assert score < 50

    def test_insufficient_data(self):
        bars = _make_bars(10)
        assert calculate_momentum(bars) == 50.0

    def test_clamped_0_100(self):
        # Extreme uptrend
        bars = _make_bars(30, base_close=50, trend=5.0)
        score = calculate_momentum(bars)
        assert 0 <= score <= 100


class TestVolatility:
    def test_low_volatility_high_score(self):
        # Very stable prices → high score
        bars = _make_bars(60, base_close=100, trend=0.01)
        score = calculate_volatility(bars)
        assert score > 70

    def test_high_volatility_low_score(self):
        # Erratic prices
        import random

        random.seed(42)
        bars = [{"close": 100 + random.uniform(-10, 10)} for _ in range(60)]
        score = calculate_volatility(bars)
        assert score < 60

    def test_insufficient_data(self):
        assert calculate_volatility(_make_bars(10)) == 50.0


class TestLiquidity:
    def test_high_volume(self):
        bars = _make_bars(30)  # 1.5M volume
        score = calculate_liquidity(bars)
        assert score == 100.0  # >=1M → capped at 100

    def test_low_volume(self):
        bars = [{"volume": 100_000, "close": 100} for _ in range(30)]
        score = calculate_liquidity(bars)
        assert score == pytest.approx(10.0)

    def test_insufficient_data(self):
        assert calculate_liquidity(_make_bars(10)) == 50.0


class TestValue:
    def test_ideal_pe(self):
        # PE=12 is the peak of the bell curve
        score = calculate_value(pe_ratio=12.0)
        assert score > 60  # PE contributes 40%, score ~100*0.4 + 50*0.6 = 70

    def test_negative_pe(self):
        score = calculate_value(pe_ratio=-5.0)
        assert score < 50

    def test_all_none(self):
        assert calculate_value() == 50.0

    def test_healthy_fundamentals(self):
        score = calculate_value(pe_ratio=15, profit_margin=0.15, current_ratio=1.5)
        assert score > 60


class TestQuality:
    def test_high_quality(self):
        score = calculate_quality(
            return_on_equity=0.20,
            debt_to_equity=0.5,
            profit_margin=0.15,
            current_ratio=1.5,
            market_cap=50_000_000_000,
        )
        assert score > 65

    def test_low_quality(self):
        score = calculate_quality(
            return_on_equity=-0.05,
            debt_to_equity=3.0,
            profit_margin=-0.10,
            current_ratio=0.5,
            market_cap=500_000_000,
        )
        assert score < 40


class TestSentiment:
    def test_bullish(self):
        score = calculate_sentiment_from_momentum(80.0)
        assert 60 <= score <= 80

    def test_bearish(self):
        score = calculate_sentiment_from_momentum(10.0)
        assert 20 <= score <= 40

    def test_neutral(self):
        score = calculate_sentiment_from_momentum(50.0)
        assert 40 <= score <= 60


class TestFinalScore:
    def test_basic_calculation(self):
        scores = FactorScores(
            momentum=80,
            value=60,
            quality=70,
            volatility=50,
            liquidity=90,
            sentiment=65,
        )
        result = calculate_final_score(scores, "moderate", "bull")
        assert Decimal("0") < result < Decimal("100")

    def test_conservative_emphasizes_quality(self):
        high_quality = FactorScores(
            quality=100, momentum=0, value=0, volatility=0, liquidity=0, sentiment=0
        )
        cons_score = calculate_final_score(high_quality, "conservative", "bull")
        aggr_score = calculate_final_score(high_quality, "aggressive", "bull")
        assert cons_score > aggr_score

    def test_aggressive_emphasizes_momentum(self):
        high_momentum = FactorScores(
            momentum=100, quality=0, value=0, volatility=0, liquidity=0, sentiment=0
        )
        cons_score = calculate_final_score(high_momentum, "conservative", "bull")
        aggr_score = calculate_final_score(high_momentum, "aggressive", "bull")
        assert aggr_score > cons_score

    def test_crisis_regime_boosts_quality(self):
        balanced = FactorScores(
            momentum=50,
            value=50,
            quality=80,
            volatility=80,
            liquidity=50,
            sentiment=50,
        )
        crisis_score = calculate_final_score(balanced, "moderate", "crisis")
        bull_score = calculate_final_score(balanced, "moderate", "bull")
        # In crisis, quality and volatility get higher multipliers
        assert crisis_score > bull_score
