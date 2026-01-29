"""
Unit tests for RiskProfile enum.

Tests cover:
- Enum values match proto UserProfile.profile_type
- to_risk_tolerance() conversion
- from_risk_tolerance() conversion with boundary conditions
- from_string() conversion
- Error handling for invalid inputs
"""

import pytest
from enum import Enum

from shared.models.risk_profile import RiskProfile


class TestRiskProfileEnum:
    """Tests for RiskProfile enum basic properties."""

    def test_inherits_from_enum(self) -> None:
        """RiskProfile must inherit from enum.Enum."""
        assert issubclass(RiskProfile, Enum)

    def test_has_three_values(self) -> None:
        """RiskProfile must have exactly three values."""
        assert len(RiskProfile) == 3

    def test_conservative_value(self) -> None:
        """CONSERVATIVE must have value 'conservative' matching proto."""
        assert RiskProfile.CONSERVATIVE.value == "conservative"

    def test_moderate_value(self) -> None:
        """MODERATE must have value 'moderate' matching proto."""
        assert RiskProfile.MODERATE.value == "moderate"

    def test_aggressive_value(self) -> None:
        """AGGRESSIVE must have value 'aggressive' matching proto."""
        assert RiskProfile.AGGRESSIVE.value == "aggressive"


class TestToRiskTolerance:
    """Tests for to_risk_tolerance() method."""

    def test_conservative_returns_0_3(self) -> None:
        """CONSERVATIVE.to_risk_tolerance() must return 0.3."""
        result = RiskProfile.CONSERVATIVE.to_risk_tolerance()
        assert result == 0.3
        assert isinstance(result, float)

    def test_moderate_returns_0_6(self) -> None:
        """MODERATE.to_risk_tolerance() must return 0.6."""
        result = RiskProfile.MODERATE.to_risk_tolerance()
        assert result == 0.6
        assert isinstance(result, float)

    def test_aggressive_returns_0_9(self) -> None:
        """AGGRESSIVE.to_risk_tolerance() must return 0.9."""
        result = RiskProfile.AGGRESSIVE.to_risk_tolerance()
        assert result == 0.9
        assert isinstance(result, float)

    def test_all_values_in_valid_range(self) -> None:
        """All tolerance values must be between 0.0 and 1.0."""
        for profile in RiskProfile:
            tolerance = profile.to_risk_tolerance()
            assert 0.0 <= tolerance <= 1.0, f"{profile} tolerance {tolerance} out of range"


class TestFromRiskTolerance:
    """Tests for from_risk_tolerance() class method."""

    def test_zero_returns_conservative(self) -> None:
        """0.0 tolerance must return CONSERVATIVE."""
        result = RiskProfile.from_risk_tolerance(0.0)
        assert result == RiskProfile.CONSERVATIVE

    def test_low_value_returns_conservative(self) -> None:
        """Values below 0.45 must return CONSERVATIVE."""
        for value in [0.1, 0.2, 0.3, 0.44, 0.449]:
            result = RiskProfile.from_risk_tolerance(value)
            assert result == RiskProfile.CONSERVATIVE, f"Expected CONSERVATIVE for {value}"

    def test_boundary_0_45_returns_moderate(self) -> None:
        """0.45 (boundary) must return MODERATE."""
        result = RiskProfile.from_risk_tolerance(0.45)
        assert result == RiskProfile.MODERATE

    def test_mid_values_return_moderate(self) -> None:
        """Values from 0.45 to below 0.75 must return MODERATE."""
        for value in [0.45, 0.5, 0.6, 0.7, 0.74, 0.749]:
            result = RiskProfile.from_risk_tolerance(value)
            assert result == RiskProfile.MODERATE, f"Expected MODERATE for {value}"

    def test_boundary_0_75_returns_aggressive(self) -> None:
        """0.75 (boundary) must return AGGRESSIVE."""
        result = RiskProfile.from_risk_tolerance(0.75)
        assert result == RiskProfile.AGGRESSIVE

    def test_high_values_return_aggressive(self) -> None:
        """Values from 0.75 to 1.0 must return AGGRESSIVE."""
        for value in [0.75, 0.8, 0.9, 0.99, 1.0]:
            result = RiskProfile.from_risk_tolerance(value)
            assert result == RiskProfile.AGGRESSIVE, f"Expected AGGRESSIVE for {value}"

    def test_raises_on_negative_value(self) -> None:
        """Negative tolerance must raise ValueError."""
        with pytest.raises(ValueError) as excinfo:
            RiskProfile.from_risk_tolerance(-0.1)
        assert "must be between 0.0 and 1.0" in str(excinfo.value)
        assert "-0.1" in str(excinfo.value)

    def test_raises_on_value_above_one(self) -> None:
        """Tolerance above 1.0 must raise ValueError."""
        with pytest.raises(ValueError) as excinfo:
            RiskProfile.from_risk_tolerance(1.1)
        assert "must be between 0.0 and 1.0" in str(excinfo.value)
        assert "1.1" in str(excinfo.value)

    def test_raises_on_large_invalid_value(self) -> None:
        """Large invalid tolerance must raise ValueError."""
        with pytest.raises(ValueError) as excinfo:
            RiskProfile.from_risk_tolerance(5.0)
        assert "must be between 0.0 and 1.0" in str(excinfo.value)


class TestFromString:
    """Tests for from_string() class method."""

    def test_conservative_string(self) -> None:
        """'conservative' string must return CONSERVATIVE."""
        result = RiskProfile.from_string("conservative")
        assert result == RiskProfile.CONSERVATIVE

    def test_moderate_string(self) -> None:
        """'moderate' string must return MODERATE."""
        result = RiskProfile.from_string("moderate")
        assert result == RiskProfile.MODERATE

    def test_aggressive_string(self) -> None:
        """'aggressive' string must return AGGRESSIVE."""
        result = RiskProfile.from_string("aggressive")
        assert result == RiskProfile.AGGRESSIVE

    def test_case_insensitive_uppercase(self) -> None:
        """Uppercase input must work (case insensitive)."""
        assert RiskProfile.from_string("CONSERVATIVE") == RiskProfile.CONSERVATIVE
        assert RiskProfile.from_string("MODERATE") == RiskProfile.MODERATE
        assert RiskProfile.from_string("AGGRESSIVE") == RiskProfile.AGGRESSIVE

    def test_case_insensitive_mixed(self) -> None:
        """Mixed case input must work (case insensitive)."""
        assert RiskProfile.from_string("Conservative") == RiskProfile.CONSERVATIVE
        assert RiskProfile.from_string("Moderate") == RiskProfile.MODERATE
        assert RiskProfile.from_string("Aggressive") == RiskProfile.AGGRESSIVE

    def test_raises_on_invalid_string(self) -> None:
        """Invalid string must raise ValueError with helpful message."""
        with pytest.raises(ValueError) as excinfo:
            RiskProfile.from_string("invalid")
        assert "Invalid profile_type" in str(excinfo.value)
        assert "invalid" in str(excinfo.value)
        assert "conservative" in str(excinfo.value)
        assert "moderate" in str(excinfo.value)
        assert "aggressive" in str(excinfo.value)

    def test_raises_on_empty_string(self) -> None:
        """Empty string must raise ValueError."""
        with pytest.raises(ValueError) as excinfo:
            RiskProfile.from_string("")
        assert "Invalid profile_type" in str(excinfo.value)


class TestRoundTripConversion:
    """Tests for round-trip conversions between profile and tolerance."""

    def test_conservative_round_trip(self) -> None:
        """CONSERVATIVE -> tolerance -> CONSERVATIVE."""
        tolerance = RiskProfile.CONSERVATIVE.to_risk_tolerance()
        result = RiskProfile.from_risk_tolerance(tolerance)
        assert result == RiskProfile.CONSERVATIVE

    def test_moderate_round_trip(self) -> None:
        """MODERATE -> tolerance -> MODERATE."""
        tolerance = RiskProfile.MODERATE.to_risk_tolerance()
        result = RiskProfile.from_risk_tolerance(tolerance)
        assert result == RiskProfile.MODERATE

    def test_aggressive_round_trip(self) -> None:
        """AGGRESSIVE -> tolerance -> AGGRESSIVE."""
        tolerance = RiskProfile.AGGRESSIVE.to_risk_tolerance()
        result = RiskProfile.from_risk_tolerance(tolerance)
        assert result == RiskProfile.AGGRESSIVE


class TestProtoCompatibility:
    """Tests to verify compatibility with proto UserProfile message."""

    def test_values_match_proto_profile_type(self) -> None:
        """All enum values must exactly match proto profile_type values."""
        # From common.proto:
        # string profile_type = 2;  // "conservative", "moderate", "aggressive"
        expected_values = {"conservative", "moderate", "aggressive"}
        actual_values = {p.value for p in RiskProfile}
        assert actual_values == expected_values

    def test_risk_tolerance_in_proto_range(self) -> None:
        """All tolerance values must be in proto's 0.0-1.0 range."""
        # From common.proto:
        # double risk_tolerance = 3;  // 0.0-1.0 scale
        for profile in RiskProfile:
            tolerance = profile.to_risk_tolerance()
            assert 0.0 <= tolerance <= 1.0


class TestTypeHints:
    """Tests to verify type hint compliance."""

    def test_to_risk_tolerance_returns_float(self) -> None:
        """to_risk_tolerance() must return a float."""
        for profile in RiskProfile:
            result = profile.to_risk_tolerance()
            assert isinstance(result, float)

    def test_from_risk_tolerance_returns_risk_profile(self) -> None:
        """from_risk_tolerance() must return a RiskProfile."""
        for value in [0.0, 0.3, 0.5, 0.7, 0.9, 1.0]:
            result = RiskProfile.from_risk_tolerance(value)
            assert isinstance(result, RiskProfile)

    def test_from_string_returns_risk_profile(self) -> None:
        """from_string() must return a RiskProfile."""
        for value in ["conservative", "moderate", "aggressive"]:
            result = RiskProfile.from_string(value)
            assert isinstance(result, RiskProfile)
