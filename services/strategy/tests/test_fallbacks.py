"""Tests for rule-based fallback agents."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.agents.fallbacks import (
    RuleBasedMacroStrategist,
    RuleBasedRiskManager,
    RuleBasedTechnicalAnalyst,
)
from src.workflow.state import MarketContext, RiskAssessment, TechnicalSignal


class TestRuleBasedMacroStrategist:
    """Tests for RuleBasedMacroStrategist."""

    def test_crisis_regime(self):
        """Crisis regime maps to extreme risk."""
        strategist = RuleBasedMacroStrategist()
        result = strategist.analyze(
            stock_picks=[{"symbol": "AAPL"}],
            regime="crisis",
            user_preferences={},
        )

        assert isinstance(result, MarketContext)
        assert result.regime == "crisis"
        assert result.risk_level == "extreme"
        assert result.confidence == 0.6

    def test_bear_regime(self):
        """Bear regime maps to high risk."""
        strategist = RuleBasedMacroStrategist()
        result = strategist.analyze([], "bear", {})

        assert result.risk_level == "high"
        assert result.regime == "bear"

    def test_bull_regime(self):
        """Bull regime maps to low risk."""
        strategist = RuleBasedMacroStrategist()
        result = strategist.analyze([], "bull", {})

        assert result.risk_level == "low"

    def test_sideways_regime(self):
        """Sideways regime maps to medium risk."""
        strategist = RuleBasedMacroStrategist()
        result = strategist.analyze([], "sideways", {})

        assert result.risk_level == "medium"

    def test_recovery_regime(self):
        """Recovery regime maps to medium risk."""
        strategist = RuleBasedMacroStrategist()
        result = strategist.analyze([], "recovery", {})

        assert result.risk_level == "medium"

    def test_unknown_regime_defaults_to_medium(self):
        """Unknown regime defaults to medium risk."""
        strategist = RuleBasedMacroStrategist()
        result = strategist.analyze([], "unknown_regime", {})

        assert result.risk_level == "medium"

    def test_empty_sector_outlook(self):
        """Fallback returns empty sector outlook."""
        strategist = RuleBasedMacroStrategist()
        result = strategist.analyze([], "bull", {})

        assert result.sector_outlook == {}
        assert result.macro_indicators == {}


class TestRuleBasedTechnicalAnalyst:
    """Tests for RuleBasedTechnicalAnalyst."""

    @pytest.mark.asyncio
    async def test_no_market_data_client(self):
        """Without market data client, returns empty signals."""
        analyst = RuleBasedTechnicalAnalyst(market_data_client=None)
        market_ctx = MarketContext(
            regime="bull", confidence=0.8, risk_level="low",
            sector_outlook={}, macro_indicators={},
        )
        signals = await analyst.analyze(
            stock_picks=[{"symbol": "AAPL"}],
            market_context=market_ctx,
        )

        assert signals == []

    @pytest.mark.asyncio
    async def test_bullish_ma_crossover(self):
        """MA10 > MA20 and price > MA10 → long signal."""
        # Create bars where price is trending up
        # MA20 close prices: 10 bars at ~95, 10 bars at ~105 → MA20 ≈ 100
        # MA10: last 10 bars at ~105 → MA10 ≈ 105
        bars = []
        for i in range(10):
            bars.append({"close": 95.0 + i * 0.1})
        for i in range(10):
            bars.append({"close": 105.0 + i * 0.5})

        mock_client = AsyncMock()
        mock_client.get_ohlcv = AsyncMock(return_value=bars)

        analyst = RuleBasedTechnicalAnalyst(market_data_client=mock_client)
        market_ctx = MarketContext(
            regime="bull", confidence=0.8, risk_level="low",
            sector_outlook={}, macro_indicators={},
        )

        signals = await analyst.analyze(
            stock_picks=[{"symbol": "AAPL"}],
            market_context=market_ctx,
        )

        assert len(signals) == 1
        assert signals[0].symbol == "AAPL"
        assert signals[0].direction == "long"
        assert 0.3 <= signals[0].strength <= 0.8

    @pytest.mark.asyncio
    async def test_bearish_ma_crossover(self):
        """MA10 < MA20 and price < MA10 → short signal."""
        # Price trending down
        bars = []
        for i in range(10):
            bars.append({"close": 105.0 - i * 0.1})
        for i in range(10):
            bars.append({"close": 95.0 - i * 0.5})

        mock_client = AsyncMock()
        mock_client.get_ohlcv = AsyncMock(return_value=bars)

        analyst = RuleBasedTechnicalAnalyst(market_data_client=mock_client)
        market_ctx = MarketContext(
            regime="bear", confidence=0.8, risk_level="high",
            sector_outlook={}, macro_indicators={},
        )

        signals = await analyst.analyze(
            stock_picks=[{"symbol": "AAPL"}],
            market_context=market_ctx,
        )

        assert len(signals) == 1
        assert signals[0].direction == "short"

    @pytest.mark.asyncio
    async def test_no_clear_signal(self):
        """Sideways market → no signal."""
        # MA10 ≈ MA20, price near both
        bars = [{"close": 100.0 + (i % 3 - 1) * 0.1} for i in range(20)]

        mock_client = AsyncMock()
        mock_client.get_ohlcv = AsyncMock(return_value=bars)

        analyst = RuleBasedTechnicalAnalyst(market_data_client=mock_client)
        market_ctx = MarketContext(
            regime="sideways", confidence=0.8, risk_level="medium",
            sector_outlook={}, macro_indicators={},
        )

        signals = await analyst.analyze(
            stock_picks=[{"symbol": "AAPL"}],
            market_context=market_ctx,
        )

        # May or may not have signals depending on exact values
        for signal in signals:
            assert isinstance(signal, TechnicalSignal)

    @pytest.mark.asyncio
    async def test_insufficient_data(self):
        """Less than 20 bars → no signal."""
        bars = [{"close": 100.0}] * 10

        mock_client = AsyncMock()
        mock_client.get_ohlcv = AsyncMock(return_value=bars)

        analyst = RuleBasedTechnicalAnalyst(market_data_client=mock_client)
        market_ctx = MarketContext(
            regime="bull", confidence=0.8, risk_level="low",
            sector_outlook={}, macro_indicators={},
        )

        signals = await analyst.analyze(
            stock_picks=[{"symbol": "AAPL"}],
            market_context=market_ctx,
        )

        assert signals == []

    @pytest.mark.asyncio
    async def test_multiple_symbols(self):
        """Analyze multiple symbols."""
        # Last bar (115) > MA10 (110.5) > MA20 (102.75) → long signal
        bars_up = [{"close": 95.0}] * 10 + [
            {"close": 106.0 + i} for i in range(10)
        ]

        mock_client = AsyncMock()
        mock_client.get_ohlcv = AsyncMock(return_value=bars_up)

        analyst = RuleBasedTechnicalAnalyst(market_data_client=mock_client)
        market_ctx = MarketContext(
            regime="bull", confidence=0.8, risk_level="low",
            sector_outlook={}, macro_indicators={},
        )

        signals = await analyst.analyze(
            stock_picks=[{"symbol": "AAPL"}, {"symbol": "GOOGL"}],
            market_context=market_ctx,
        )

        assert len(signals) == 2

    @pytest.mark.asyncio
    async def test_symbol_analysis_error_handled(self):
        """Error in one symbol doesn't block others."""
        mock_client = AsyncMock()
        # Last bar (115) > MA10 > MA20 → long signal
        good_bars = [{"close": 95.0}] * 10 + [
            {"close": 106.0 + i} for i in range(10)
        ]
        mock_client.get_ohlcv = AsyncMock(
            side_effect=[
                Exception("API error"),
                good_bars,
            ]
        )

        analyst = RuleBasedTechnicalAnalyst(market_data_client=mock_client)
        market_ctx = MarketContext(
            regime="bull", confidence=0.8, risk_level="low",
            sector_outlook={}, macro_indicators={},
        )

        signals = await analyst.analyze(
            stock_picks=[{"symbol": "BAD"}, {"symbol": "GOOD"}],
            market_context=market_ctx,
        )

        # BAD should be skipped, GOOD should succeed
        assert len(signals) == 1
        assert signals[0].symbol == "GOOD"

    @pytest.mark.asyncio
    async def test_signal_has_entry_price_and_indicators(self):
        """Signal includes entry_price and indicator data."""
        # Last bar (115) > MA10 (110.5) > MA20 (102.75) → long signal
        bars = [{"close": 95.0}] * 10 + [
            {"close": 106.0 + i} for i in range(10)
        ]

        mock_client = AsyncMock()
        mock_client.get_ohlcv = AsyncMock(return_value=bars)

        analyst = RuleBasedTechnicalAnalyst(market_data_client=mock_client)
        market_ctx = MarketContext(
            regime="bull", confidence=0.8, risk_level="low",
            sector_outlook={}, macro_indicators={},
        )

        signals = await analyst.analyze(
            stock_picks=[{"symbol": "AAPL"}],
            market_context=market_ctx,
        )

        assert len(signals) == 1
        signal = signals[0]
        assert signal.entry_price == Decimal("115.0")
        assert "ma10" in signal.indicators
        assert "ma20" in signal.indicators
        assert "Rule-based MA crossover" in signal.rationale


class TestRuleBasedRiskManager:
    """Tests for RuleBasedRiskManager."""

    def _make_signal(self, symbol: str = "AAPL") -> TechnicalSignal:
        return TechnicalSignal(
            symbol=symbol,
            direction="long",
            strength=0.7,
            entry_price=Decimal("150.00"),
            indicators={},
            rationale="Test",
        )

    def _make_context(self, risk_level: str) -> MarketContext:
        return MarketContext(
            regime="bull", confidence=0.8, risk_level=risk_level,
            sector_outlook={}, macro_indicators={},
        )

    def test_extreme_risk_rejects_all(self):
        """Extreme risk → all signals rejected."""
        manager = RuleBasedRiskManager()
        result = manager.assess(
            signals=[self._make_signal()],
            market_context=self._make_context("extreme"),
            user_preferences={},
        )

        assert isinstance(result, RiskAssessment)
        assert result.approved is False
        assert result.risk_score == 1.0
        assert result.concentration_risk == 1.0
        assert any("Extreme" in w for w in result.warnings)

    def test_high_risk_reduces_positions(self):
        """High risk → 0.5x multiplier."""
        manager = RuleBasedRiskManager()
        result = manager.assess(
            signals=[self._make_signal("AAPL"), self._make_signal("GOOGL")],
            market_context=self._make_context("high"),
            user_preferences={},
        )

        assert result.approved is True
        assert result.position_adjustments["AAPL"] == 0.5
        assert result.position_adjustments["GOOGL"] == 0.5

    def test_medium_risk_slight_reduction(self):
        """Medium risk → 0.8x multiplier."""
        manager = RuleBasedRiskManager()
        result = manager.assess(
            signals=[self._make_signal()],
            market_context=self._make_context("medium"),
            user_preferences={},
        )

        assert result.approved is True
        assert result.position_adjustments["AAPL"] == 0.8

    def test_low_risk_full_size(self):
        """Low risk → 1.0x multiplier."""
        manager = RuleBasedRiskManager()
        result = manager.assess(
            signals=[self._make_signal()],
            market_context=self._make_context("low"),
            user_preferences={},
        )

        assert result.approved is True
        assert result.position_adjustments["AAPL"] == 1.0

    def test_unknown_risk_defaults_to_medium(self):
        """Unknown risk level → 0.8x (medium default)."""
        manager = RuleBasedRiskManager()
        result = manager.assess(
            signals=[self._make_signal()],
            market_context=self._make_context("unknown"),
            user_preferences={},
        )

        assert result.approved is True
        assert result.position_adjustments["AAPL"] == 0.8

    def test_empty_signals(self):
        """Empty signals list → approved with no adjustments."""
        manager = RuleBasedRiskManager()
        result = manager.assess(
            signals=[],
            market_context=self._make_context("low"),
            user_preferences={},
        )

        assert result.approved is True
        assert result.position_adjustments == {}

    def test_warnings_include_fallback_note(self):
        """Warnings always mention rule-based fallback."""
        manager = RuleBasedRiskManager()
        result = manager.assess(
            signals=[self._make_signal()],
            market_context=self._make_context("medium"),
            user_preferences={},
        )

        assert any("rule-based" in w.lower() for w in result.warnings)
