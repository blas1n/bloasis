"""
Unit tests for MarketRegime enum.

Tests cover:
- Enum values match proto GetCurrentRegimeResponse.regime
- get_sector_bias() conversion for all regimes
- from_string() conversion with case insensitivity
- Error handling for invalid inputs
- Type hints compliance
"""

import pytest
from enum import Enum

from shared.models.market_regime import MarketRegime


class TestMarketRegimeEnum:
    """Tests for MarketRegime enum basic properties."""

    def test_inherits_from_enum(self) -> None:
        """MarketRegime must inherit from enum.Enum."""
        assert issubclass(MarketRegime, Enum)

    def test_has_five_values(self) -> None:
        """MarketRegime must have exactly five values."""
        assert len(MarketRegime) == 5

    def test_crisis_value(self) -> None:
        """CRISIS must have value 'crisis' matching proto."""
        assert MarketRegime.CRISIS.value == "crisis"

    def test_bear_value(self) -> None:
        """BEAR must have value 'bear' matching proto."""
        assert MarketRegime.BEAR.value == "bear"

    def test_bull_value(self) -> None:
        """BULL must have value 'bull' matching proto."""
        assert MarketRegime.BULL.value == "bull"

    def test_sideways_value(self) -> None:
        """SIDEWAYS must have value 'sideways' matching proto."""
        assert MarketRegime.SIDEWAYS.value == "sideways"

    def test_recovery_value(self) -> None:
        """RECOVERY must have value 'recovery' matching proto."""
        assert MarketRegime.RECOVERY.value == "recovery"


class TestGetSectorBias:
    """Tests for get_sector_bias() method."""

    def test_crisis_returns_defensive(self) -> None:
        """CRISIS.get_sector_bias() must return 'defensive'."""
        result = MarketRegime.CRISIS.get_sector_bias()
        assert result == "defensive"
        assert isinstance(result, str)

    def test_bear_returns_balanced_defensive(self) -> None:
        """BEAR.get_sector_bias() must return 'balanced_defensive'."""
        result = MarketRegime.BEAR.get_sector_bias()
        assert result == "balanced_defensive"
        assert isinstance(result, str)

    def test_bull_returns_balanced_growth(self) -> None:
        """BULL.get_sector_bias() must return 'balanced_growth'."""
        result = MarketRegime.BULL.get_sector_bias()
        assert result == "balanced_growth"
        assert isinstance(result, str)

    def test_sideways_returns_neutral(self) -> None:
        """SIDEWAYS.get_sector_bias() must return 'neutral'."""
        result = MarketRegime.SIDEWAYS.get_sector_bias()
        assert result == "neutral"
        assert isinstance(result, str)

    def test_recovery_returns_growth(self) -> None:
        """RECOVERY.get_sector_bias() must return 'growth'."""
        result = MarketRegime.RECOVERY.get_sector_bias()
        assert result == "growth"
        assert isinstance(result, str)

    def test_all_regimes_have_valid_bias(self) -> None:
        """All regimes must have a non-empty sector bias."""
        valid_biases = {
            "defensive",
            "balanced_defensive",
            "balanced_growth",
            "neutral",
            "growth",
        }
        for regime in MarketRegime:
            bias = regime.get_sector_bias()
            assert bias in valid_biases, f"{regime} has unexpected bias: {bias}"


class TestFromString:
    """Tests for from_string() class method."""

    def test_crisis_string(self) -> None:
        """'crisis' string must return CRISIS."""
        result = MarketRegime.from_string("crisis")
        assert result == MarketRegime.CRISIS

    def test_bear_string(self) -> None:
        """'bear' string must return BEAR."""
        result = MarketRegime.from_string("bear")
        assert result == MarketRegime.BEAR

    def test_bull_string(self) -> None:
        """'bull' string must return BULL."""
        result = MarketRegime.from_string("bull")
        assert result == MarketRegime.BULL

    def test_sideways_string(self) -> None:
        """'sideways' string must return SIDEWAYS."""
        result = MarketRegime.from_string("sideways")
        assert result == MarketRegime.SIDEWAYS

    def test_recovery_string(self) -> None:
        """'recovery' string must return RECOVERY."""
        result = MarketRegime.from_string("recovery")
        assert result == MarketRegime.RECOVERY

    def test_case_insensitive_uppercase(self) -> None:
        """Uppercase input must work (case insensitive)."""
        assert MarketRegime.from_string("CRISIS") == MarketRegime.CRISIS
        assert MarketRegime.from_string("BEAR") == MarketRegime.BEAR
        assert MarketRegime.from_string("BULL") == MarketRegime.BULL
        assert MarketRegime.from_string("SIDEWAYS") == MarketRegime.SIDEWAYS
        assert MarketRegime.from_string("RECOVERY") == MarketRegime.RECOVERY

    def test_case_insensitive_mixed(self) -> None:
        """Mixed case input must work (case insensitive)."""
        assert MarketRegime.from_string("Crisis") == MarketRegime.CRISIS
        assert MarketRegime.from_string("Bear") == MarketRegime.BEAR
        assert MarketRegime.from_string("Bull") == MarketRegime.BULL
        assert MarketRegime.from_string("Sideways") == MarketRegime.SIDEWAYS
        assert MarketRegime.from_string("Recovery") == MarketRegime.RECOVERY

    def test_raises_on_invalid_string(self) -> None:
        """Invalid string must raise ValueError with helpful message."""
        with pytest.raises(ValueError) as excinfo:
            MarketRegime.from_string("invalid")
        assert "Invalid regime" in str(excinfo.value)
        assert "invalid" in str(excinfo.value)
        assert "crisis" in str(excinfo.value)

    def test_raises_on_empty_string(self) -> None:
        """Empty string must raise ValueError."""
        with pytest.raises(ValueError) as excinfo:
            MarketRegime.from_string("")
        assert "Invalid regime" in str(excinfo.value)

    def test_raises_on_legacy_values(self) -> None:
        """Legacy regime values must raise ValueError."""
        legacy_values = ["normal_bull", "normal_bear", "euphoria", "high_volatility", "low_volatility"]
        for legacy in legacy_values:
            with pytest.raises(ValueError):
                MarketRegime.from_string(legacy)


class TestProtoCompatibility:
    """Tests to verify compatibility with proto GetCurrentRegimeResponse message."""

    def test_values_match_proto_regime(self) -> None:
        """All enum values must exactly match proto regime values."""
        # From market_regime.proto GetCurrentRegimeResponse:
        # string regime = 1;
        # Documented values: "crisis", "bear", "bull", "sideways", "recovery"
        expected_values = {
            "crisis",
            "bear",
            "bull",
            "sideways",
            "recovery",
        }
        actual_values = {r.value for r in MarketRegime}
        assert actual_values == expected_values


class TestTierSystem:
    """Tests related to the Tier 1-2-3 system."""

    def test_crisis_regime_has_defensive_bias(self) -> None:
        """Crisis regime should have defensive bias."""
        assert MarketRegime.CRISIS.get_sector_bias() == "defensive"

    def test_bear_regime_has_balanced_defensive_bias(self) -> None:
        """Bear regime should have balanced_defensive bias."""
        assert MarketRegime.BEAR.get_sector_bias() == "balanced_defensive"

    def test_bull_regime_has_balanced_growth_bias(self) -> None:
        """Bull regime should have balanced_growth bias."""
        assert MarketRegime.BULL.get_sector_bias() == "balanced_growth"

    def test_sideways_has_neutral_bias(self) -> None:
        """Sideways regime should have neutral bias."""
        assert MarketRegime.SIDEWAYS.get_sector_bias() == "neutral"

    def test_recovery_has_growth_bias(self) -> None:
        """Recovery regime should have growth bias."""
        assert MarketRegime.RECOVERY.get_sector_bias() == "growth"


class TestTypeHints:
    """Tests to verify type hint compliance."""

    def test_get_sector_bias_returns_str(self) -> None:
        """get_sector_bias() must return a str."""
        for regime in MarketRegime:
            result = regime.get_sector_bias()
            assert isinstance(result, str)

    def test_from_string_returns_market_regime(self) -> None:
        """from_string() must return a MarketRegime."""
        for value in ["crisis", "bear", "bull", "sideways", "recovery"]:
            result = MarketRegime.from_string(value)
            assert isinstance(result, MarketRegime)


class TestDocstrings:
    """Tests to verify docstrings are present."""

    def test_class_has_docstring(self) -> None:
        """MarketRegime class must have a docstring."""
        assert MarketRegime.__doc__ is not None
        assert len(MarketRegime.__doc__) > 100  # Non-trivial docstring

    def test_get_sector_bias_has_docstring(self) -> None:
        """get_sector_bias() method must have a docstring."""
        assert MarketRegime.get_sector_bias.__doc__ is not None
        assert "sector bias" in MarketRegime.get_sector_bias.__doc__.lower()

    def test_from_string_has_docstring(self) -> None:
        """from_string() method must have a docstring."""
        assert MarketRegime.from_string.__doc__ is not None
        assert "string" in MarketRegime.from_string.__doc__.lower()
