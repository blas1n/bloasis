"""Tests for core/prompts/ — no mocks needed."""

from app.core.prompts.analysis import format_analysis_prompt
from app.core.prompts.regime import format_regime_prompt
from app.core.prompts.sector import format_sector_prompt


class TestRegimePrompt:
    def test_formats_with_data(self):
        result = format_regime_prompt(
            market_data={"vix": 25.5, "sp500_1m_change": -3.2},
            macro_indicators={"fed_funds_rate": 5.25},
        )
        assert "25.5" in result
        assert "-3.2" in result
        assert "5.25" in result

    def test_defaults_for_missing_data(self):
        result = format_regime_prompt({}, {})
        assert "N/A" in result

    def test_contains_classification_guidelines(self):
        result = format_regime_prompt({}, {})
        assert "crisis" in result
        assert "bear" in result
        assert "bull" in result


class TestAnalysisPrompt:
    def test_formats_with_data(self):
        result = format_analysis_prompt(
            stock_data=[{"symbol": "AAPL", "score": 85}],
            ohlcv_summary="AAPL: RSI=65, MACD=bullish",
            market_context={"regime": "bull", "risk_level": "low"},
            user_preferences={"risk_profile": "moderate", "max_single_position": 0.10},
        )
        assert "AAPL" in result
        assert "bull" in result
        assert "moderate" in result
        assert "10" in result  # max_single_position as percentage

    def test_excluded_sectors(self):
        result = format_analysis_prompt(
            stock_data=[],
            ohlcv_summary="",
            market_context={},
            user_preferences={"excluded_sectors": ["Energy", "Utilities"]},
        )
        assert "Energy" in result
        assert "Utilities" in result


class TestSectorPrompt:
    def test_formats_with_data(self):
        result = format_sector_prompt(
            symbols=["AAPL", "MSFT"],
            regime="bull",
            sectors=["Technology", "Healthcare"],
        )
        assert "AAPL" in result
        assert "bull" in result
        assert "Technology" in result

    def test_empty_inputs(self):
        result = format_sector_prompt([], "", [])
        assert "None" in result or "unknown" in result
