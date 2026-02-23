"""Unit tests for Signal Generator (ATR-based SL/TP + volatility sizing)."""

from decimal import Decimal

import pytest

from src.agents.signal_generator import (
    _MAX_SIZE,
    _RISK_MULT,
    _TARGET_VOL,
    SignalGenerator,
)
from src.workflow.state import MarketContext, RiskAssessment, TechnicalSignal


@pytest.fixture
def generator():
    return SignalGenerator()


@pytest.fixture
def market_context():
    return MarketContext(
        regime="normal_bull",
        confidence=0.8,
        risk_level="medium",
        sector_outlook={"Technology": 0.8},
        macro_indicators={},
    )


@pytest.fixture
def risk_assessment():
    return RiskAssessment(
        approved=True,
        risk_score=0.3,
        position_adjustments={"AAPL": 1.0, "TSLA": 0.8},
        warnings=[],
        concentration_risk=0.2,
    )


def _make_bars(n: int, base: float = 150.0, volatility: float = 2.0) -> list[dict]:
    """Generate synthetic OHLCV bars."""
    bars = []
    for i in range(n):
        c = base + (i % 5) * volatility
        bars.append({
            "open": c - 0.5,
            "high": c + volatility,
            "low": c - volatility,
            "close": c,
            "volume": 1_000_000,
        })
    return bars


class TestSignalGeneration:
    """Tests for generate()."""

    def test_generate_basic(self, generator, market_context, risk_assessment):
        """Generate signals from technical signals."""
        signals = [
            TechnicalSignal(
                symbol="AAPL",
                direction="long",
                strength=0.8,
                entry_price=Decimal("150.00"),
                indicators={},
                rationale="Strong momentum",
            ),
        ]

        result = generator.generate(
            technical_signals=signals,
            risk_assessment=risk_assessment,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
        )

        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert result[0].action == "buy"
        assert result[0].confidence == 0.8
        assert result[0].risk_approved is True

    def test_generate_with_ohlcv_data(self, generator, market_context, risk_assessment):
        """Generate signals with OHLCV data for ATR calculation."""
        signals = [
            TechnicalSignal(
                symbol="AAPL",
                direction="long",
                strength=0.7,
                entry_price=Decimal("150.00"),
                indicators={},
                rationale="Bullish crossover",
            ),
        ]

        ohlcv_data = {"AAPL": _make_bars(60)}

        result = generator.generate(
            technical_signals=signals,
            risk_assessment=risk_assessment,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
            ohlcv_data=ohlcv_data,
        )

        assert len(result) == 1
        # With ATR data, SL/TP should be set dynamically
        assert result[0].stop_loss < result[0].entry_price  # Long → SL below entry
        assert result[0].take_profit > result[0].entry_price  # Long → TP above entry

    def test_generate_short_direction(self, generator, market_context, risk_assessment):
        """Short signals should have inverted SL/TP."""
        signals = [
            TechnicalSignal(
                symbol="AAPL",
                direction="short",
                strength=0.6,
                entry_price=Decimal("150.00"),
                indicators={},
                rationale="Bearish divergence",
            ),
        ]

        ohlcv_data = {"AAPL": _make_bars(60)}

        result = generator.generate(
            technical_signals=signals,
            risk_assessment=risk_assessment,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
            ohlcv_data=ohlcv_data,
        )

        assert result[0].action == "sell"
        assert result[0].stop_loss > result[0].entry_price  # Short → SL above entry
        assert result[0].take_profit < result[0].entry_price  # Short → TP below entry

    def test_generate_neutral_direction(self, generator, market_context, risk_assessment):
        """Neutral signal maps to hold action."""
        signals = [
            TechnicalSignal(
                symbol="AAPL",
                direction="neutral",
                strength=0.5,
                entry_price=Decimal("150.00"),
                indicators={},
                rationale="Mixed signals",
            ),
        ]

        result = generator.generate(
            technical_signals=signals,
            risk_assessment=risk_assessment,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
        )

        assert result[0].action == "hold"

    def test_generate_multiple_signals(self, generator, market_context, risk_assessment):
        """Generate multiple signals at once."""
        signals = [
            TechnicalSignal(
                symbol="AAPL",
                direction="long",
                strength=0.8,
                entry_price=Decimal("150.00"),
                indicators={},
                rationale="Buy",
            ),
            TechnicalSignal(
                symbol="TSLA",
                direction="short",
                strength=0.6,
                entry_price=Decimal("200.00"),
                indicators={},
                rationale="Sell",
            ),
        ]

        result = generator.generate(
            technical_signals=signals,
            risk_assessment=risk_assessment,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
        )

        assert len(result) == 2
        assert result[0].symbol == "AAPL"
        assert result[1].symbol == "TSLA"

    def test_risk_adjustment_applied(self, generator, market_context, risk_assessment):
        """Position adjustment from risk assessment should be applied."""
        signals = [
            TechnicalSignal(
                symbol="TSLA",
                direction="long",
                strength=0.8,
                entry_price=Decimal("200.00"),
                indicators={},
                rationale="Buy",
            ),
        ]

        # TSLA has 0.8x adjustment in risk_assessment
        result = generator.generate(
            technical_signals=signals,
            risk_assessment=risk_assessment,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
        )

        # Size should be reduced by 0.8x multiplier
        no_adj_signals = [
            TechnicalSignal(
                symbol="NONADJ",
                direction="long",
                strength=0.8,
                entry_price=Decimal("200.00"),
                indicators={},
                rationale="Buy",
            ),
        ]
        risk_no_adj = RiskAssessment(
            approved=True,
            risk_score=0.3,
            position_adjustments={"NONADJ": 1.0},
            warnings=[],
            concentration_risk=0.2,
        )
        result_no_adj = generator.generate(
            technical_signals=no_adj_signals,
            risk_assessment=risk_no_adj,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
        )

        # The adjusted signal should have a smaller size
        assert result[0].size_recommendation <= result_no_adj[0].size_recommendation


class TestCalculateBaseSizeVolatility:
    """Tests for _calculate_base_size with volatility adjustment."""

    def test_base_size_within_limits(self, generator):
        """Size should never exceed max_size for risk profile."""
        for profile in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE"):
            size = generator._calculate_base_size(
                strength=1.0,
                risk_profile=profile,
                atr=5.0,
                entry_price=150.0,
            )
            assert size <= _MAX_SIZE[profile]

    def test_zero_atr_no_vol_adjustment(self, generator):
        """Without ATR, no volatility adjustment is applied."""
        size_no_atr = generator._calculate_base_size(
            strength=0.8, risk_profile="MODERATE", atr=0.0, entry_price=150.0,
        )
        # Should be strength * max_size (no vol adjustment)
        expected = (Decimal("0.8") * _MAX_SIZE["MODERATE"]).quantize(Decimal("0.0001"))
        assert size_no_atr == expected

    def test_high_volatility_reduces_size(self, generator):
        """High ATR (volatility) should reduce position size."""
        size_low_vol = generator._calculate_base_size(
            strength=0.8, risk_profile="MODERATE", atr=1.0, entry_price=150.0,
        )
        size_high_vol = generator._calculate_base_size(
            strength=0.8, risk_profile="MODERATE", atr=10.0, entry_price=150.0,
        )
        assert size_high_vol <= size_low_vol

    def test_conservative_smaller_than_aggressive(self, generator):
        """Conservative profile should produce smaller sizes."""
        size_cons = generator._calculate_base_size(
            strength=0.8, risk_profile="CONSERVATIVE", atr=3.0, entry_price=150.0,
        )
        size_aggr = generator._calculate_base_size(
            strength=0.8, risk_profile="AGGRESSIVE", atr=3.0, entry_price=150.0,
        )
        assert size_cons < size_aggr

    def test_size_precision(self, generator):
        """Size should be quantized to 4 decimal places."""
        size = generator._calculate_base_size(
            strength=0.7, risk_profile="MODERATE", atr=3.0, entry_price=150.0,
        )
        assert size == size.quantize(Decimal("0.0001"))


class TestCalculateLevelsATR:
    """Tests for ATR-based stop-loss and take-profit."""

    def test_long_atr_levels(self, generator, market_context):
        """Long signal: SL below entry, TP above entry."""
        signal = TechnicalSignal(
            symbol="AAPL", direction="long", strength=0.8,
            entry_price=Decimal("150.00"), indicators={}, rationale="",
        )
        sl, tp = generator._calculate_levels(signal, market_context, atr=3.0)

        assert sl < Decimal("150.00")
        assert tp > Decimal("150.00")

    def test_short_atr_levels(self, generator, market_context):
        """Short signal: SL above entry, TP below entry."""
        signal = TechnicalSignal(
            symbol="AAPL", direction="short", strength=0.8,
            entry_price=Decimal("150.00"), indicators={}, rationale="",
        )
        sl, tp = generator._calculate_levels(signal, market_context, atr=3.0)

        assert sl > Decimal("150.00")
        assert tp < Decimal("150.00")

    def test_atr_distances_use_risk_mult(self, generator):
        """Different risk levels should produce different SL/TP distances."""
        signal = TechnicalSignal(
            symbol="AAPL", direction="long", strength=0.8,
            entry_price=Decimal("150.00"), indicators={}, rationale="",
        )

        ctx_low = MarketContext(
            regime="normal_bull", confidence=0.8, risk_level="low",
            sector_outlook={}, macro_indicators={},
        )
        ctx_extreme = MarketContext(
            regime="crisis", confidence=0.8, risk_level="extreme",
            sector_outlook={}, macro_indicators={},
        )

        sl_low, tp_low = generator._calculate_levels(signal, ctx_low, atr=3.0)
        sl_ext, tp_ext = generator._calculate_levels(signal, ctx_extreme, atr=3.0)

        # Low risk = wider bands (1.25x), extreme = tighter bands (0.5x)
        assert (Decimal("150.00") - sl_low) > (Decimal("150.00") - sl_ext)
        assert (tp_low - Decimal("150.00")) > (tp_ext - Decimal("150.00"))

    def test_fallback_when_no_atr(self, generator, market_context):
        """When ATR=0, fallback to fixed percentage."""
        signal = TechnicalSignal(
            symbol="AAPL", direction="long", strength=0.8,
            entry_price=Decimal("150.00"), indicators={}, rationale="",
        )
        sl, tp = generator._calculate_levels(signal, market_context, atr=0.0)

        # Should still have valid SL/TP
        assert sl < Decimal("150.00")
        assert tp > Decimal("150.00")

    def test_atr_sl_distance_formula(self, generator):
        """Verify SL = entry - 2 * ATR * risk_mult for long."""
        signal = TechnicalSignal(
            symbol="AAPL", direction="long", strength=0.8,
            entry_price=Decimal("100.00"), indicators={}, rationale="",
        )
        ctx = MarketContext(
            regime="normal_bull", confidence=0.8, risk_level="medium",
            sector_outlook={}, macro_indicators={},
        )

        sl, tp = generator._calculate_levels(signal, ctx, atr=5.0)

        # medium risk_mult = 1.0
        expected_sl = Decimal("100.00") - Decimal("2") * Decimal("5.0") * Decimal("1.0")
        expected_tp = Decimal("100.00") + Decimal("3") * Decimal("5.0") * Decimal("1.0")

        assert sl == expected_sl  # 100 - 10 = 90
        assert tp == expected_tp  # 100 + 15 = 115


class TestFallbackPercentages:
    """Tests for _fallback_pct."""

    def test_long_extreme_risk(self, generator):
        sl_pct, tp_pct = generator._fallback_pct("long", "extreme")
        assert sl_pct == Decimal("0.995")  # 1 - 0.005
        assert tp_pct == Decimal("1.02")  # 1 + 0.02

    def test_short_extreme_risk(self, generator):
        sl_pct, tp_pct = generator._fallback_pct("short", "extreme")
        assert sl_pct == Decimal("1.005")  # 1 + 0.005
        assert tp_pct == Decimal("0.98")  # 1 - 0.02

    def test_long_medium_risk(self, generator):
        sl_pct, tp_pct = generator._fallback_pct("long", "medium")
        assert sl_pct == Decimal("0.98")  # 1 - 0.02
        assert tp_pct == Decimal("1.05")  # 1 + 0.05


class TestSignalToAction:
    """Tests for _signal_to_action."""

    def test_long_to_buy(self, generator):
        assert generator._signal_to_action("long") == "buy"

    def test_short_to_sell(self, generator):
        assert generator._signal_to_action("short") == "sell"

    def test_neutral_to_hold(self, generator):
        assert generator._signal_to_action("neutral") == "hold"

    def test_unknown_to_hold(self, generator):
        assert generator._signal_to_action("unknown") == "hold"


class TestRiskMultipliers:
    """Tests for risk multiplier constants."""

    def test_risk_mult_ordering(self):
        """Extreme < high < medium < low."""
        assert _RISK_MULT["extreme"] < _RISK_MULT["high"]
        assert _RISK_MULT["high"] < _RISK_MULT["medium"]
        assert _RISK_MULT["medium"] < _RISK_MULT["low"]

    def test_target_vol_ordering(self):
        """Conservative < moderate < aggressive."""
        assert _TARGET_VOL["CONSERVATIVE"] < _TARGET_VOL["MODERATE"]
        assert _TARGET_VOL["MODERATE"] < _TARGET_VOL["AGGRESSIVE"]

    def test_max_size_ordering(self):
        """Conservative < moderate < aggressive."""
        assert _MAX_SIZE["CONSERVATIVE"] < _MAX_SIZE["MODERATE"]
        assert _MAX_SIZE["MODERATE"] < _MAX_SIZE["AGGRESSIVE"]
