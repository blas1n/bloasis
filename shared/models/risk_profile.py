"""
Risk Profile Enumeration for BLOASIS Trading Platform.

This module provides the RiskProfile enum class that maps to the UserProfile.profile_type
field in common.proto. It supports bidirectional conversion between risk profile enums
and risk tolerance float values (0.0-1.0).

Reference: shared/proto/common.proto UserProfile message
"""

from enum import Enum


class RiskProfile(Enum):
    """
    Enumeration of user risk profile types.

    Maps directly to the UserProfile.profile_type values in common.proto:
    - "conservative": Low risk tolerance (0.3)
    - "moderate": Medium risk tolerance (0.6)
    - "aggressive": High risk tolerance (0.9)

    Attributes:
        CONSERVATIVE: Conservative risk profile with low risk tolerance.
        MODERATE: Moderate risk profile with balanced risk tolerance.
        AGGRESSIVE: Aggressive risk profile with high risk tolerance.

    Example:
        >>> profile = RiskProfile.MODERATE
        >>> profile.value
        'moderate'
        >>> tolerance = profile.to_risk_tolerance()
        >>> tolerance
        0.6
        >>> RiskProfile.from_risk_tolerance(0.5)
        <RiskProfile.MODERATE: 'moderate'>
    """

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

    def to_risk_tolerance(self) -> float:
        """
        Convert RiskProfile to a risk tolerance float value.

        Maps each risk profile to a representative float value in the 0.0-1.0 range:
        - CONSERVATIVE -> 0.3 (low risk tolerance)
        - MODERATE -> 0.6 (medium risk tolerance)
        - AGGRESSIVE -> 0.9 (high risk tolerance)

        Returns:
            float: Risk tolerance value between 0.0 and 1.0.

        Example:
            >>> RiskProfile.CONSERVATIVE.to_risk_tolerance()
            0.3
            >>> RiskProfile.MODERATE.to_risk_tolerance()
            0.6
            >>> RiskProfile.AGGRESSIVE.to_risk_tolerance()
            0.9
        """
        tolerance_map: dict[RiskProfile, float] = {
            RiskProfile.CONSERVATIVE: 0.3,
            RiskProfile.MODERATE: 0.6,
            RiskProfile.AGGRESSIVE: 0.9,
        }
        return tolerance_map[self]

    @classmethod
    def from_risk_tolerance(cls, tolerance: float) -> "RiskProfile":
        """
        Convert a risk tolerance float value to a RiskProfile enum.

        Maps float values in the 0.0-1.0 range to risk profiles:
        - 0.0 to 0.45 (exclusive) -> CONSERVATIVE
        - 0.45 to 0.75 (exclusive) -> MODERATE
        - 0.75 to 1.0 (inclusive) -> AGGRESSIVE

        Args:
            tolerance: A float value between 0.0 and 1.0 representing risk tolerance.

        Returns:
            RiskProfile: The corresponding risk profile enum.

        Raises:
            ValueError: If tolerance is not in the valid range [0.0, 1.0].

        Example:
            >>> RiskProfile.from_risk_tolerance(0.2)
            <RiskProfile.CONSERVATIVE: 'conservative'>
            >>> RiskProfile.from_risk_tolerance(0.5)
            <RiskProfile.MODERATE: 'moderate'>
            >>> RiskProfile.from_risk_tolerance(0.8)
            <RiskProfile.AGGRESSIVE: 'aggressive'>
            >>> RiskProfile.from_risk_tolerance(0.45)
            <RiskProfile.MODERATE: 'moderate'>
            >>> RiskProfile.from_risk_tolerance(0.75)
            <RiskProfile.AGGRESSIVE: 'aggressive'>
        """
        if not 0.0 <= tolerance <= 1.0:
            raise ValueError(
                f"Risk tolerance must be between 0.0 and 1.0, got {tolerance}"
            )

        if tolerance < 0.45:
            return cls.CONSERVATIVE
        elif tolerance < 0.75:
            return cls.MODERATE
        else:
            return cls.AGGRESSIVE

    @classmethod
    def from_string(cls, profile_type: str) -> "RiskProfile":
        """
        Convert a string value to a RiskProfile enum.

        This method provides a convenient way to convert the profile_type string
        from the proto UserProfile message to a RiskProfile enum.

        Args:
            profile_type: A string value matching one of the enum values
                         ("conservative", "moderate", "aggressive").

        Returns:
            RiskProfile: The corresponding risk profile enum.

        Raises:
            ValueError: If profile_type is not a valid risk profile string.

        Example:
            >>> RiskProfile.from_string("conservative")
            <RiskProfile.CONSERVATIVE: 'conservative'>
            >>> RiskProfile.from_string("moderate")
            <RiskProfile.MODERATE: 'moderate'>
            >>> RiskProfile.from_string("aggressive")
            <RiskProfile.AGGRESSIVE: 'aggressive'>
        """
        try:
            return cls(profile_type.lower())
        except ValueError:
            valid_values = [p.value for p in cls]
            raise ValueError(
                f"Invalid profile_type '{profile_type}'. "
                f"Must be one of: {valid_values}"
            )
