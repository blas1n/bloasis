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

    def test_has_six_values(self) -> None:
        """MarketRegime must have exactly six values."""
        assert len(MarketRegime) == 6

    def test_crisis_value(self) -> None:
        """CRISIS must have value 'crisis' matching proto."""
        assert MarketRegime.CRISIS.value == "crisis"

    def test_normal_bear_value(self) -> None:
        """NORMAL_BEAR must have value 'normal_bear' matching proto."""
        assert MarketRegime.NORMAL_BEAR.value == "normal_bear"

    def test_normal_bull_value(self) -> None:
        """NORMAL_BULL must have value 'normal_bull' matching proto."""
        assert MarketRegime.NORMAL_BULL.value == "normal_bull"

    def test_euphoria_value(self) -> None:
        """EUPHORIA must have value 'euphoria' matching proto."""
        assert MarketRegime.EUPHORIA.value == "euphoria"

    def test_high_volatility_value(self) -> None:
        """HIGH_VOLATILITY must have value 'high_volatility' matching proto."""
        assert MarketRegime.HIGH_VOLATILITY.value == "high_volatility"

    def test_low_volatility_value(self) -> None:
        """LOW_VOLATILITY must have value 'low_volatility' matching proto."""
        assert MarketRegime.LOW_VOLATILITY.value == "low_volatility"


class TestGetSectorBias:
    """Tests for get_sector_bias() method."""

    def test_crisis_returns_defensive(self) -> None:
        """CRISIS.get_sector_bias() must return 'defensive'."""
        result = MarketRegime.CRISIS.get_sector_bias()
        assert result == "defensive"
        assert isinstance(result, str)

    def test_normal_bear_returns_balanced_defensive(self) -> None:
        """NORMAL_BEAR.get_sector_bias() must return 'balanced_defensive'."""
        result = MarketRegime.NORMAL_BEAR.get_sector_bias()
        assert result == "balanced_defensive"
        assert isinstance(result, str)

    def test_normal_bull_returns_balanced_growth(self) -> None:
        """NORMAL_BULL.get_sector_bias() must return 'balanced_growth'."""
        result = MarketRegime.NORMAL_BULL.get_sector_bias()
        assert result == "balanced_growth"
        assert isinstance(result, str)

    def test_euphoria_returns_speculative(self) -> None:
        """EUPHORIA.get_sector_bias() must return 'speculative'."""
        result = MarketRegime.EUPHORIA.get_sector_bias()
        assert result == "speculative"
        assert isinstance(result, str)

    def test_high_volatility_returns_defensive(self) -> None:
        """HIGH_VOLATILITY.get_sector_bias() must return 'defensive'."""
        result = MarketRegime.HIGH_VOLATILITY.get_sector_bias()
        assert result == "defensive"
        assert isinstance(result, str)

    def test_low_volatility_returns_growth(self) -> None:
        """LOW_VOLATILITY.get_sector_bias() must return 'growth'."""
        result = MarketRegime.LOW_VOLATILITY.get_sector_bias()
        assert result == "growth"
        assert isinstance(result, str)

    def test_all_regimes_have_valid_bias(self) -> None:
        """All regimes must have a non-empty sector bias."""
        valid_biases = {
            "defensive",
            "balanced_defensive",
            "balanced_growth",
            "speculative",
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

    def test_normal_bear_string(self) -> None:
        """'normal_bear' string must return NORMAL_BEAR."""
        result = MarketRegime.from_string("normal_bear")
        assert result == MarketRegime.NORMAL_BEAR

    def test_normal_bull_string(self) -> None:
        """'normal_bull' string must return NORMAL_BULL."""
        result = MarketRegime.from_string("normal_bull")
        assert result == MarketRegime.NORMAL_BULL

    def test_euphoria_string(self) -> None:
        """'euphoria' string must return EUPHORIA."""
        result = MarketRegime.from_string("euphoria")
        assert result == MarketRegime.EUPHORIA

    def test_high_volatility_string(self) -> None:
        """'high_volatility' string must return HIGH_VOLATILITY."""
        result = MarketRegime.from_string("high_volatility")
        assert result == MarketRegime.HIGH_VOLATILITY

    def test_low_volatility_string(self) -> None:
        """'low_volatility' string must return LOW_VOLATILITY."""
        result = MarketRegime.from_string("low_volatility")
        assert result == MarketRegime.LOW_VOLATILITY

    def test_case_insensitive_uppercase(self) -> None:
        """Uppercase input must work (case insensitive)."""
        assert MarketRegime.from_string("CRISIS") == MarketRegime.CRISIS
        assert MarketRegime.from_string("NORMAL_BEAR") == MarketRegime.NORMAL_BEAR
        assert MarketRegime.from_string("NORMAL_BULL") == MarketRegime.NORMAL_BULL
        assert MarketRegime.from_string("EUPHORIA") == MarketRegime.EUPHORIA
        assert MarketRegime.from_string("HIGH_VOLATILITY") == MarketRegime.HIGH_VOLATILITY
        assert MarketRegime.from_string("LOW_VOLATILITY") == MarketRegime.LOW_VOLATILITY

    def test_case_insensitive_mixed(self) -> None:
        """Mixed case input must work (case insensitive)."""
        assert MarketRegime.from_string("Crisis") == MarketRegime.CRISIS
        assert MarketRegime.from_string("Normal_Bear") == MarketRegime.NORMAL_BEAR
        assert MarketRegime.from_string("Normal_Bull") == MarketRegime.NORMAL_BULL
        assert MarketRegime.from_string("Euphoria") == MarketRegime.EUPHORIA
        assert MarketRegime.from_string("High_Volatility") == MarketRegime.HIGH_VOLATILITY
        assert MarketRegime.from_string("Low_Volatility") == MarketRegime.LOW_VOLATILITY

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

    def test_raises_on_partial_match(self) -> None:
        """Partial match must raise ValueError."""
        with pytest.raises(ValueError):
            MarketRegime.from_string("bull")
        with pytest.raises(ValueError):
            MarketRegime.from_string("bear")
        with pytest.raises(ValueError):
            MarketRegime.from_string("volatility")


class TestProtoCompatibility:
    """Tests to verify compatibility with proto GetCurrentRegimeResponse message."""

    def test_values_match_proto_regime(self) -> None:
        """All enum values must exactly match proto regime values."""
        # From market_regime.proto GetCurrentRegimeResponse:
        # string regime = 1;
        # Documented values: "crisis", "normal_bear", "normal_bull",
        #                    "euphoria", "high_volatility", "low_volatility"
        expected_values = {
            "crisis",
            "normal_bear",
            "normal_bull",
            "euphoria",
            "high_volatility",
            "low_volatility",
        }
        actual_values = {r.value for r in MarketRegime}
        assert actual_values == expected_values


class TestTierSystem:
    """Tests related to the Tier 1-2-3 system."""

    def test_defensive_regimes_have_defensive_bias(self) -> None:
        """Crisis and high volatility regimes should have defensive bias."""
        defensive_regimes = [MarketRegime.CRISIS, MarketRegime.HIGH_VOLATILITY]
        for regime in defensive_regimes:
            assert regime.get_sector_bias() == "defensive"

    def test_bear_regime_has_balanced_defensive_bias(self) -> None:
        """Normal bear regime should have balanced_defensive bias."""
        assert MarketRegime.NORMAL_BEAR.get_sector_bias() == "balanced_defensive"

    def test_bull_regime_has_balanced_growth_bias(self) -> None:
        """Normal bull regime should have balanced_growth bias."""
        assert MarketRegime.NORMAL_BULL.get_sector_bias() == "balanced_growth"

    def test_euphoria_has_speculative_bias(self) -> None:
        """Euphoria regime should have speculative bias."""
        assert MarketRegime.EUPHORIA.get_sector_bias() == "speculative"

    def test_low_volatility_has_growth_bias(self) -> None:
        """Low volatility regime should have growth bias."""
        assert MarketRegime.LOW_VOLATILITY.get_sector_bias() == "growth"


class TestTypeHints:
    """Tests to verify type hint compliance."""

    def test_get_sector_bias_returns_str(self) -> None:
        """get_sector_bias() must return a str."""
        for regime in MarketRegime:
            result = regime.get_sector_bias()
            assert isinstance(result, str)

    def test_from_string_returns_market_regime(self) -> None:
        """from_string() must return a MarketRegime."""
        for value in [
            "crisis",
            "normal_bear",
            "normal_bull",
            "euphoria",
            "high_volatility",
            "low_volatility",
        ]:
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
