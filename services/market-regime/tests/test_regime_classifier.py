"""
Unit tests for RegimeClassifier (Claude AI + rule-based fallback).
"""

from unittest.mock import AsyncMock

import pytest

from src.models import RegimeClassifier, RegimeData


class TestRegimeClassifierFallback:
    """Tests for RegimeClassifier._fallback_classify() (no analyst)."""

    @pytest.mark.asyncio
    async def test_fallback_crisis_high_vix(self) -> None:
        """VIX > 30 → crisis regime."""
        classifier = RegimeClassifier()  # analyst=None
        result = await classifier.classify(market_data={"vix": 35.0}, macro_indicators={})

        assert result.regime == "crisis"
        assert result.confidence == 0.85
        assert result.risk_level == "high"

    @pytest.mark.asyncio
    async def test_fallback_bear_elevated_vix(self) -> None:
        """25 < VIX <= 30 → bear regime."""
        classifier = RegimeClassifier()
        result = await classifier.classify(market_data={"vix": 28.0}, macro_indicators={})

        assert result.regime == "bear"
        assert result.confidence == 0.75
        assert result.risk_level == "medium"

    @pytest.mark.asyncio
    async def test_fallback_bull_low_vix(self) -> None:
        """VIX < 15 → bull regime."""
        classifier = RegimeClassifier()
        result = await classifier.classify(market_data={"vix": 12.0}, macro_indicators={})

        assert result.regime == "bull"
        assert result.confidence == 0.80
        assert result.risk_level == "low"

    @pytest.mark.asyncio
    async def test_fallback_sideways_moderate_vix(self) -> None:
        """15 <= VIX <= 25 → sideways regime."""
        classifier = RegimeClassifier()
        result = await classifier.classify(market_data={"vix": 20.0}, macro_indicators={})

        assert result.regime == "sideways"
        assert result.confidence == 0.65

    @pytest.mark.asyncio
    async def test_fallback_default_data(self) -> None:
        """No market data → uses defaults (VIX=20 → sideways)."""
        classifier = RegimeClassifier()
        result = await classifier.classify()

        assert result.regime == "sideways"
        assert result.confidence == 0.65
        assert isinstance(result, RegimeData)

    @pytest.mark.asyncio
    async def test_fallback_timestamp_format(self) -> None:
        """Timestamp should be valid ISO 8601."""
        classifier = RegimeClassifier()
        result = await classifier.classify()

        assert "T" in result.timestamp
        assert result.timestamp.endswith("+00:00") or result.timestamp.endswith("Z")

    @pytest.mark.asyncio
    async def test_fallback_includes_indicators(self) -> None:
        """Result should include indicator dict."""
        classifier = RegimeClassifier()
        result = await classifier.classify(
            market_data={"vix": 20.0, "sp500_trend": "up"},
            macro_indicators={"yield_curve_10y_2y": 0.5},
        )

        assert result.indicators is not None
        assert "vix" in result.indicators
        assert result.indicators["vix"] == 20.0


class TestRegimeClassifierClaude:
    """Tests for RegimeClassifier with Claude analyst."""

    @pytest.mark.asyncio
    async def test_classify_claude_success(self) -> None:
        """Should use Claude result when analyst returns valid response."""
        mock_analyst = AsyncMock()
        mock_analyst.analyze = AsyncMock(return_value={
            "regime": "crisis",
            "confidence": 0.95,
            "reasoning": "Extreme market stress",
            "key_indicators": ["vix", "credit_spreads"],
        })

        classifier = RegimeClassifier(analyst=mock_analyst)
        result = await classifier.classify()

        assert result.regime == "crisis"
        assert result.confidence == 0.95
        assert result.risk_level == "high"
        mock_analyst.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_classify_claude_failure_uses_fallback(self) -> None:
        """Should fall back to rule-based when Claude raises an exception."""
        mock_analyst = AsyncMock()
        mock_analyst.analyze = AsyncMock(side_effect=Exception("API error"))

        classifier = RegimeClassifier(analyst=mock_analyst)
        result = await classifier.classify(market_data={"vix": 20.0}, macro_indicators={})

        # Default VIX=20 → sideways fallback
        assert result.regime == "sideways"
        assert result.confidence == 0.65

    @pytest.mark.asyncio
    async def test_classify_claude_empty_response_uses_parse_defaults(self) -> None:
        """Empty Claude response → _parse_regime_response defaults → sideways."""
        mock_analyst = AsyncMock()
        mock_analyst.analyze = AsyncMock(return_value={})

        classifier = RegimeClassifier(analyst=mock_analyst)
        result = await classifier.classify()

        assert result.regime == "sideways"

    @pytest.mark.asyncio
    async def test_classify_claude_passes_correct_model(self) -> None:
        """Should pass the configured model to analyst.analyze."""
        mock_analyst = AsyncMock()
        mock_analyst.analyze = AsyncMock(return_value={
            "regime": "bull", "confidence": 0.8, "reasoning": "Low VIX",
        })

        classifier = RegimeClassifier(analyst=mock_analyst, claude_model="claude-haiku-4-5-20251001")
        await classifier.classify()

        call_kwargs = mock_analyst.analyze.call_args[1]
        assert call_kwargs.get("model") == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_classify_claude_passes_json_format(self) -> None:
        """Should request JSON response format from Claude."""
        mock_analyst = AsyncMock()
        mock_analyst.analyze = AsyncMock(return_value={
            "regime": "sideways", "confidence": 0.65, "reasoning": "Mixed",
        })

        classifier = RegimeClassifier(analyst=mock_analyst)
        await classifier.classify()

        call_kwargs = mock_analyst.analyze.call_args[1]
        assert call_kwargs.get("response_format") == "json"

    @pytest.mark.asyncio
    async def test_classify_timestamp_iso8601(self) -> None:
        """Claude path should return valid ISO 8601 timestamp."""
        mock_analyst = AsyncMock()
        mock_analyst.analyze = AsyncMock(return_value={
            "regime": "bull", "confidence": 0.9, "reasoning": "baseline",
        })

        classifier = RegimeClassifier(analyst=mock_analyst)
        result = await classifier.classify()

        assert "T" in result.timestamp
        assert result.timestamp.endswith("+00:00") or result.timestamp.endswith("Z")


class TestParseRegimeResponse:
    """Tests for RegimeClassifier._parse_regime_response()."""

    def setup_method(self) -> None:
        self.classifier = RegimeClassifier()

    def test_valid_regime_passes_through(self) -> None:
        """Valid regime value should be returned unchanged."""
        data = {"regime": "bull", "confidence": 0.85, "reasoning": "Low VIX", "key_indicators": ["vix"]}
        result = self.classifier._parse_regime_response(data)

        assert result["regime"] == "bull"
        assert result["confidence"] == 0.85
        assert result["reasoning"] == "Low VIX"
        assert result["indicators"] == ["vix"]

    def test_invalid_regime_defaults_to_sideways(self) -> None:
        """Unknown regime string should fall back to 'sideways'."""
        data = {"regime": "unknown_value", "confidence": 0.75}
        result = self.classifier._parse_regime_response(data)

        assert result["regime"] == "sideways"
        assert result["confidence"] == 0.75

    def test_confidence_clamped_above_one(self) -> None:
        """Confidence > 1.0 should be clamped to 1.0."""
        data = {"regime": "bull", "confidence": 1.5}
        result = self.classifier._parse_regime_response(data)

        assert result["confidence"] == 1.0

    def test_confidence_clamped_below_zero(self) -> None:
        """Confidence < 0.0 should be clamped to 0.0."""
        data = {"regime": "bear", "confidence": -0.3}
        result = self.classifier._parse_regime_response(data)

        assert result["confidence"] == 0.0

    def test_empty_response_returns_defaults(self) -> None:
        """Empty dict should return safe defaults."""
        result = self.classifier._parse_regime_response({})

        assert result["regime"] == "sideways"
        assert result["confidence"] == 0.5

    def test_all_valid_regimes_accepted(self) -> None:
        """All five regime values should be accepted."""
        valid_regimes = ["crisis", "bear", "bull", "sideways", "recovery"]
        for regime in valid_regimes:
            result = self.classifier._parse_regime_response({"regime": regime, "confidence": 0.7})
            assert result["regime"] == regime, f"Expected {regime} to be accepted"


class TestCalculateRiskLevel:
    """Tests for RegimeClassifier._calculate_risk_level()."""

    def setup_method(self) -> None:
        self.classifier = RegimeClassifier()

    def test_crisis_is_high_risk(self) -> None:
        assert self.classifier._calculate_risk_level("crisis", 25.0) == "high"

    def test_high_vix_is_high_risk(self) -> None:
        assert self.classifier._calculate_risk_level("sideways", 35.0) == "high"

    def test_bear_is_medium_risk(self) -> None:
        assert self.classifier._calculate_risk_level("bear", 18.0) == "medium"

    def test_elevated_vix_is_medium_risk(self) -> None:
        assert self.classifier._calculate_risk_level("sideways", 22.0) == "medium"

    def test_bull_is_low_risk(self) -> None:
        assert self.classifier._calculate_risk_level("bull", 12.0) == "low"
