"""Tests for AI agents (Macro Strategist, Technical Analyst, Risk Manager, Signal Generator)."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.agents.macro_strategist import MacroStrategist
from src.agents.risk_manager import RiskManager
from src.agents.signal_generator import SignalGenerator
from src.agents.technical_analyst import TechnicalAnalyst
from src.workflow.state import MarketContext, RiskAssessment, TechnicalSignal


class TestMacroStrategist:
    """Tests for Macro Strategist agent."""

    @pytest.fixture
    def mock_fingpt_client(self):
        """Create mock FinGPT client."""
        client = AsyncMock()
        client.analyze = AsyncMock(
            return_value={
                "risk_level": "medium",
                "sector_outlook": {"Technology": 75, "Healthcare": 60},
                "macro_indicators": {"inflation": "rising", "rates": "stable"},
            }
        )
        return client

    @pytest.fixture
    def strategist(self, mock_fingpt_client):
        """Create Macro Strategist with mock client."""
        return MacroStrategist(fingpt_client=mock_fingpt_client)

    @pytest.mark.asyncio
    async def test_analyze_success(self, strategist, mock_fingpt_client):
        """Test successful macro analysis."""
        stock_picks = [
            {"symbol": "AAPL", "sector": "Technology"},
            {"symbol": "MSFT", "sector": "Technology"},
        ]

        result = await strategist.analyze(
            stock_picks=stock_picks,
            regime="normal_bull",
            user_preferences={"risk_profile": "MODERATE"},
        )

        assert isinstance(result, MarketContext)
        assert result.regime == "normal_bull"
        assert result.risk_level == "medium"
        assert "Technology" in result.sector_outlook
        mock_fingpt_client.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_fallback_on_error(self, strategist, mock_fingpt_client):
        """Test fallback to safe defaults on analysis error."""
        mock_fingpt_client.analyze.side_effect = Exception("API error")

        stock_picks = [{"symbol": "AAPL", "sector": "Technology"}]

        result = await strategist.analyze(
            stock_picks=stock_picks,
            regime="normal_bull",
            user_preferences={},
        )

        # Should return fallback context
        assert isinstance(result, MarketContext)
        assert result.confidence == 0.5
        assert result.risk_level == "medium"

    @pytest.mark.asyncio
    async def test_assess_regime_risk(self, strategist, mock_fingpt_client):
        """Test regime risk assessment."""
        # Mock analyze method (shared FinGPT client uses analyze)
        mock_fingpt_client.analyze = AsyncMock(
            return_value={
                "confidence": 0.9,
                "risk_level": "high",
                "factors": ["vix_spike"],
            }
        )

        result = await strategist.assess_regime_risk(
            regime="crisis",
            indicators={"vix": 35},
        )

        assert result["confidence"] == 0.9
        assert result["risk_level"] == "high"


class TestTechnicalAnalyst:
    """Tests for Technical Analyst agent."""

    @pytest.fixture
    def mock_claude_client(self):
        """Create mock Claude client."""
        client = AsyncMock()
        # Mock the analyze method (used with YAML prompts)
        client.analyze = AsyncMock(
            return_value=[
                {
                    "symbol": "AAPL",
                    "direction": "long",
                    "strength": 0.75,
                    "entry_price": 150.25,
                    "indicators": {"rsi": 65},
                    "rationale": "Strong momentum",
                }
            ]
        )
        return client

    @pytest.fixture
    def mock_market_data_client(self):
        """Create mock Market Data client."""
        client = AsyncMock()
        client.get_ohlcv = AsyncMock(
            return_value=[
                {
                    "timestamp": "2024-01-01",
                    "close": 150.25,
                    "volume": 1000000,
                }
            ]
        )
        return client

    @pytest.fixture
    def analyst(self, mock_claude_client, mock_market_data_client):
        """Create Technical Analyst with mock clients."""
        return TechnicalAnalyst(
            claude_client=mock_claude_client,
            market_data_client=mock_market_data_client,
        )

    @pytest.fixture
    def market_context(self):
        """Create test market context."""
        return MarketContext(
            regime="normal_bull",
            confidence=0.8,
            risk_level="medium",
            sector_outlook={"Technology": 75},
            macro_indicators={},
        )

    @pytest.mark.asyncio
    async def test_analyze_success(
        self, analyst, market_context, mock_claude_client, mock_market_data_client
    ):
        """Test successful technical analysis."""
        stock_picks = [{"symbol": "AAPL", "sector": "Technology"}]

        result = await analyst.analyze(
            stock_picks=stock_picks,
            market_context=market_context,
        )

        assert len(result) == 1
        assert isinstance(result[0], TechnicalSignal)
        assert result[0].symbol == "AAPL"
        assert result[0].direction == "long"
        mock_market_data_client.get_ohlcv.assert_called_once()
        mock_claude_client.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_with_ohlcv_error(self, analyst, market_context, mock_market_data_client):
        """Test analysis when OHLCV fetch fails."""
        mock_market_data_client.get_ohlcv.side_effect = Exception("API error")

        stock_picks = [{"symbol": "AAPL", "sector": "Technology"}]

        result = await analyst.analyze(
            stock_picks=stock_picks,
            market_context=market_context,
        )

        # Should still attempt analysis with empty OHLCV data
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_analyze_claude_error(self, analyst, market_context, mock_claude_client):
        """Test analysis when Claude API fails."""
        mock_claude_client.analyze.side_effect = Exception("Claude error")

        stock_picks = [{"symbol": "AAPL", "sector": "Technology"}]

        result = await analyst.analyze(
            stock_picks=stock_picks,
            market_context=market_context,
        )

        # Should return empty list on error
        assert result == []


class TestRiskManager:
    """Tests for Risk Manager agent."""

    @pytest.fixture
    def mock_claude_client(self):
        """Create mock Claude client."""
        client = AsyncMock()
        # Mock the analyze method (used with YAML prompts)
        client.analyze = AsyncMock(
            return_value={
                "approved": True,
                "risk_score": 0.4,
                "position_adjustments": {"AAPL": 0.8},
                "concentration_risk": 0.3,
                "warnings": [],
            }
        )
        return client

    @pytest.fixture
    def manager(self, mock_claude_client):
        """Create Risk Manager with mock client."""
        return RiskManager(claude_client=mock_claude_client)

    @pytest.fixture
    def market_context(self):
        """Create test market context."""
        return MarketContext(
            regime="normal_bull",
            confidence=0.8,
            risk_level="medium",
            sector_outlook={},
            macro_indicators={},
        )

    @pytest.fixture
    def technical_signals(self):
        """Create test technical signals."""
        return [
            TechnicalSignal(
                symbol="AAPL",
                direction="long",
                strength=0.75,
                entry_price=Decimal("150.25"),
                indicators={},
                rationale="Strong momentum",
            )
        ]

    @pytest.mark.asyncio
    async def test_assess_success(
        self, manager, technical_signals, market_context, mock_claude_client
    ):
        """Test successful risk assessment."""
        result = await manager.assess(
            signals=technical_signals,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
        )

        assert isinstance(result, RiskAssessment)
        assert result.approved is True
        assert result.risk_score == 0.4
        mock_claude_client.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_assess_rejection(self, manager, mock_claude_client):
        """Test risk assessment with rejection."""
        mock_claude_client.analyze.return_value = {
            "approved": False,
            "risk_score": 0.9,
            "position_adjustments": {},
            "concentration_risk": 0.8,
            "warnings": ["High concentration risk"],
        }

        result = await manager.assess(
            signals=[],
            market_context=MarketContext(
                regime="crisis",
                confidence=0.8,
                risk_level="extreme",
                sector_outlook={},
                macro_indicators={},
            ),
            user_preferences={},
        )

        assert result.approved is False
        assert result.risk_score == 0.9

    @pytest.mark.asyncio
    async def test_assess_error_failsafe(
        self, manager, technical_signals, market_context, mock_claude_client
    ):
        """Test fail-safe rejection on error."""
        mock_claude_client.analyze.side_effect = Exception("API error")

        result = await manager.assess(
            signals=technical_signals,
            market_context=market_context,
            user_preferences={},
        )

        # Should fail-safe to rejection
        assert result.approved is False
        assert result.risk_score == 1.0


class TestSignalGenerator:
    """Tests for Signal Generator."""

    @pytest.fixture
    def generator(self):
        """Create Signal Generator."""
        return SignalGenerator()

    @pytest.fixture
    def market_context(self):
        """Create test market context."""
        return MarketContext(
            regime="normal_bull",
            confidence=0.8,
            risk_level="medium",
            sector_outlook={},
            macro_indicators={},
        )

    @pytest.fixture
    def technical_signals(self):
        """Create test technical signals."""
        return [
            TechnicalSignal(
                symbol="AAPL",
                direction="long",
                strength=0.75,
                entry_price=Decimal("150.00"),
                indicators={},
                rationale="Strong momentum",
            )
        ]

    @pytest.fixture
    def risk_assessment(self):
        """Create test risk assessment."""
        return RiskAssessment(
            approved=True,
            risk_score=0.4,
            position_adjustments={"AAPL": 0.8},
            warnings=[],
            concentration_risk=0.3,
        )

    def test_generate_signals(self, generator, technical_signals, risk_assessment, market_context):
        """Test trading signal generation."""
        result = generator.generate(
            technical_signals=technical_signals,
            risk_assessment=risk_assessment,
            market_context=market_context,
            user_preferences={"risk_profile": "MODERATE"},
        )

        assert len(result) == 1
        signal = result[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.confidence == 0.75
        assert signal.risk_approved is True

    def test_calculate_base_size_conservative(self, generator):
        """Test position size calculation for conservative profile."""
        size = generator._calculate_base_size(strength=0.8, risk_profile="CONSERVATIVE")
        assert size == Decimal("0.04")  # 0.8 * 0.05

    def test_calculate_base_size_aggressive(self, generator):
        """Test position size calculation for aggressive profile."""
        size = generator._calculate_base_size(strength=0.8, risk_profile="AGGRESSIVE")
        assert size == Decimal("0.12")  # 0.8 * 0.15

    def test_calculate_levels_long(self, generator, technical_signals, market_context):
        """Test stop-loss and take-profit calculation for long position."""
        signal = technical_signals[0]
        stop_loss, take_profit = generator._calculate_levels(signal, market_context)

        assert stop_loss < signal.entry_price
        assert take_profit > signal.entry_price

    def test_calculate_levels_high_risk(self, generator, technical_signals):
        """Test tighter stops in high risk environment."""
        high_risk_context = MarketContext(
            regime="crisis",
            confidence=0.8,
            risk_level="high",
            sector_outlook={},
            macro_indicators={},
        )

        signal = technical_signals[0]
        stop_loss, take_profit = generator._calculate_levels(signal, high_risk_context)

        # Stops should be tighter in high risk
        assert stop_loss == signal.entry_price * Decimal("0.99")

    def test_signal_to_action(self, generator):
        """Test signal direction to action conversion."""
        assert generator._signal_to_action("long") == "buy"
        assert generator._signal_to_action("short") == "sell"
        assert generator._signal_to_action("neutral") == "hold"
