"""Tests for core/regime_classifier.py — no mocks needed."""

from app.core.regime_classifier import calculate_risk_level, parse_regime_response


class TestParseRegimeResponse:
    def test_valid_response(self):
        data = {
            "regime": "crisis",
            "confidence": 0.95,
            "reasoning": "VIX at 40, major drawdown",
            "key_indicators": ["VIX", "S&P500"],
        }
        result = parse_regime_response(data)
        assert result["regime"] == "crisis"
        assert result["confidence"] == 0.95
        assert result["reasoning"] == "VIX at 40, major drawdown"

    def test_invalid_regime_defaults_sideways(self):
        result = parse_regime_response({"regime": "unknown_regime"})
        assert result["regime"] == "sideways"

    def test_missing_regime(self):
        result = parse_regime_response({})
        assert result["regime"] == "sideways"
        assert result["confidence"] == 0.5

    def test_confidence_clamped(self):
        result = parse_regime_response({"confidence": 1.5})
        assert result["confidence"] == 1.0

        result = parse_regime_response({"confidence": -0.5})
        assert result["confidence"] == 0.0

    def test_all_valid_regimes(self):
        for regime in ["crisis", "bear", "bull", "sideways", "recovery"]:
            result = parse_regime_response({"regime": regime})
            assert result["regime"] == regime

    def test_parse_error_returns_defaults(self):
        result = parse_regime_response({"confidence": "not_a_number"})
        assert result["regime"] == "sideways"
        assert result["confidence"] == 0.5


class TestCalculateRiskLevel:
    def test_crisis_is_extreme(self):
        assert calculate_risk_level("crisis", 25.0) == "extreme"

    def test_extreme_vix_is_extreme(self):
        assert calculate_risk_level("bull", 45.0) == "extreme"

    def test_vix_40_is_extreme(self):
        assert calculate_risk_level("bull", 40.0) == "extreme"

    def test_high_vix_is_high(self):
        assert calculate_risk_level("bull", 35.0) == "high"

    def test_vix_30_is_high(self):
        assert calculate_risk_level("bull", 30.0) == "high"

    def test_bear_is_high(self):
        assert calculate_risk_level("bear", 18.0) == "high"

    def test_moderate_vix_is_medium(self):
        assert calculate_risk_level("bull", 22.0) == "medium"

    def test_calm_bull_is_low(self):
        assert calculate_risk_level("bull", 15.0) == "low"

    def test_recovery_low_vix_is_low(self):
        assert calculate_risk_level("recovery", 18.0) == "low"
