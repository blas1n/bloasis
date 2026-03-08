"""Tests for core/signal_generator.py — no mocks needed."""

from decimal import Decimal

from app.core.models import RiskProfile
from app.core.signal_generator import generate_signal


def _make_ohlcv(n: int = 60, base: float = 100.0, atr_approx: float = 2.0) -> list[dict]:
    """Generate synthetic OHLCV bars with approximate ATR."""
    bars = []
    for i in range(n):
        c = base + (i * 0.1)  # Slight uptrend
        bars.append(
            {
                "open": c - 0.5,
                "high": c + atr_approx / 2,
                "low": c - atr_approx / 2,
                "close": c,
                "volume": 1_000_000,
            }
        )
    return bars


class TestBasicSignalGeneration:
    def test_long_signal(self):
        signal = generate_signal(
            symbol="AAPL",
            direction="long",
            strength=0.8,
            entry_price=Decimal("150"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(),
        )
        assert signal.action == "buy"
        assert signal.symbol == "AAPL"
        assert signal.stop_loss < signal.entry_price
        assert signal.take_profit > signal.entry_price

    def test_short_signal(self):
        signal = generate_signal(
            symbol="TSLA",
            direction="short",
            strength=0.6,
            entry_price=Decimal("200"),
            risk_level="high",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(base=200.0),
        )
        assert signal.action == "sell"
        assert signal.stop_loss > signal.entry_price
        assert signal.take_profit < signal.entry_price

    def test_neutral_is_hold(self):
        signal = generate_signal(
            symbol="IBM",
            direction="neutral",
            strength=0.3,
            entry_price=Decimal("130"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
        )
        assert signal.action == "hold"


class TestATRLevels:
    def test_wider_atr_wider_levels(self):
        narrow = generate_signal(
            symbol="A",
            direction="long",
            strength=0.7,
            entry_price=Decimal("100"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(atr_approx=1.0),
        )
        wide = generate_signal(
            symbol="A",
            direction="long",
            strength=0.7,
            entry_price=Decimal("100"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(atr_approx=5.0),
        )
        # Wider ATR → wider SL distance
        narrow_sl_dist = narrow.entry_price - narrow.stop_loss
        wide_sl_dist = wide.entry_price - wide.stop_loss
        assert wide_sl_dist > narrow_sl_dist

    def test_fallback_when_no_ohlcv(self):
        signal = generate_signal(
            symbol="XYZ",
            direction="long",
            strength=0.5,
            entry_price=Decimal("100"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=None,
        )
        # Should still have SL/TP via fallback percentages
        assert signal.stop_loss > 0
        assert signal.take_profit > 0


class TestProfitTiers:
    def test_three_tiers(self):
        signal = generate_signal(
            symbol="AAPL",
            direction="long",
            strength=0.8,
            entry_price=Decimal("150"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(),
        )
        assert len(signal.profit_tiers) == 3
        # Tier 1 + Tier 2 + Tier 3 percentages should sum to 1.0
        total_pct = sum(t.size_pct for t in signal.profit_tiers)
        assert total_pct == Decimal("1.00")

    def test_trailing_stop_exists(self):
        signal = generate_signal(
            symbol="AAPL",
            direction="long",
            strength=0.8,
            entry_price=Decimal("150"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(),
        )
        assert signal.trailing_stop_pct > 0


class TestPositionSizing:
    def test_conservative_smaller_than_aggressive(self):
        cons = generate_signal(
            symbol="A",
            direction="long",
            strength=0.8,
            entry_price=Decimal("100"),
            risk_level="medium",
            risk_profile=RiskProfile.CONSERVATIVE,
            ohlcv_bars=_make_ohlcv(),
        )
        aggr = generate_signal(
            symbol="A",
            direction="long",
            strength=0.8,
            entry_price=Decimal("100"),
            risk_level="medium",
            risk_profile=RiskProfile.AGGRESSIVE,
            ohlcv_bars=_make_ohlcv(),
        )
        assert cons.size_recommendation < aggr.size_recommendation

    def test_risk_adjustment_reduces_size(self):
        full = generate_signal(
            symbol="A",
            direction="long",
            strength=0.8,
            entry_price=Decimal("100"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(),
            position_adjustment=1.0,
        )
        reduced = generate_signal(
            symbol="A",
            direction="long",
            strength=0.8,
            entry_price=Decimal("100"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(),
            position_adjustment=0.5,
        )
        assert reduced.size_recommendation < full.size_recommendation


class TestRiskLevelEffect:
    def test_extreme_risk_tighter_levels(self):
        medium = generate_signal(
            symbol="A",
            direction="long",
            strength=0.7,
            entry_price=Decimal("100"),
            risk_level="medium",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(),
        )
        extreme = generate_signal(
            symbol="A",
            direction="long",
            strength=0.7,
            entry_price=Decimal("100"),
            risk_level="extreme",
            risk_profile=RiskProfile.MODERATE,
            ohlcv_bars=_make_ohlcv(),
        )
        # Extreme risk → smaller ATR multiplier → tighter SL
        medium_sl_dist = medium.entry_price - medium.stop_loss
        extreme_sl_dist = extreme.entry_price - extreme.stop_loss
        assert extreme_sl_dist < medium_sl_dist
