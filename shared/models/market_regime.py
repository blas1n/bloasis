"""
Market Regime Enumeration for BLOASIS Trading Platform.

This module provides the MarketRegime enum class that maps to the regime field
in the GetCurrentRegimeResponse message in market_regime.proto. It provides
bidirectional conversion between market regimes and sector bias strategies.

Market regimes are part of Tier 1 (shared across all users, cached for 6 hours)
and are classified using FinGPT analysis based on market conditions like VIX levels,
price trends, and sentiment indicators.

Reference: shared/proto/market_regime.proto GetCurrentRegimeResponse message

Tier System:
    - Tier 1: Market Regime Classification (this module) - Shared, 6-hour cache
    - Tier 2: Sector Strategy Generation - Shared, based on regime
    - Tier 3: User Personalization - Per-user, based on risk profile
"""

from enum import Enum


class MarketRegime(Enum):
    """
    Enumeration of market regime classifications.

    Maps directly to the GetCurrentRegimeResponse.regime values in market_regime.proto:
    - "crisis": High volatility, risk-off (VIX > 30, major drawdowns)
    - "bear": Declining market, moderate volatility
    - "bull": Rising market, low-moderate volatility
    - "sideways": Range-bound, no clear direction
    - "recovery": Transition from crisis/bear to bull

    Tier 1 Classification:
        Market regime classification is shared across ALL users and cached for 6 hours
        to optimize FinGPT API costs. This shared analysis forms the foundation for
        Tier 2 sector strategies and Tier 3 user personalization.

    FinGPT Integration:
        FinGPT analyzes multiple market indicators to classify the current regime:
        - VIX levels and volatility patterns
        - Market breadth and momentum
        - Sentiment indicators
        - Economic data trends

    Sector Strategy Influence:
        Each regime maps to a sector bias that influences Tier 2 strategy generation:
        - Crisis -> Defensive sectors (utilities, healthcare, consumer staples)
        - Bear -> Balanced defensive with some value plays
        - Bull -> Balanced growth with cyclical exposure
        - Sideways -> Neutral, balanced allocation
        - Recovery -> Growth-oriented with moderate risk

    Attributes:
        CRISIS: Crisis regime - High volatility, risk-off conditions.
        BEAR: Bear regime - Declining market with moderate volatility.
        BULL: Bull regime - Rising market with low-moderate volatility.
        SIDEWAYS: Sideways regime - Range-bound, no clear direction.
        RECOVERY: Recovery regime - Transition from crisis/bear to bull.

    Example:
        >>> regime = MarketRegime.BULL
        >>> regime.value
        'bull'
        >>> bias = regime.get_sector_bias()
        >>> bias
        'balanced_growth'
        >>> MarketRegime.from_string("crisis")
        <MarketRegime.CRISIS: 'crisis'>
    """

    CRISIS = "crisis"
    BEAR = "bear"
    BULL = "bull"
    SIDEWAYS = "sideways"
    RECOVERY = "recovery"

    def get_sector_bias(self) -> str:
        """
        Convert MarketRegime to a sector bias string.

        Maps each market regime to a recommended sector allocation strategy:
        - CRISIS -> "defensive": Focus on utilities, healthcare, consumer staples
        - BEAR -> "balanced_defensive": Mix of defensive with value opportunities
        - BULL -> "balanced_growth": Blend of growth and cyclical sectors
        - SIDEWAYS -> "neutral": Balanced allocation across sectors
        - RECOVERY -> "growth": Favor growth and technology sectors

        Returns:
            str: Sector bias string for Tier 2 strategy generation.

        Example:
            >>> MarketRegime.CRISIS.get_sector_bias()
            'defensive'
            >>> MarketRegime.BEAR.get_sector_bias()
            'balanced_defensive'
            >>> MarketRegime.BULL.get_sector_bias()
            'balanced_growth'
            >>> MarketRegime.SIDEWAYS.get_sector_bias()
            'neutral'
            >>> MarketRegime.RECOVERY.get_sector_bias()
            'growth'
        """
        bias_map: dict[MarketRegime, str] = {
            MarketRegime.CRISIS: "defensive",
            MarketRegime.BEAR: "balanced_defensive",
            MarketRegime.BULL: "balanced_growth",
            MarketRegime.SIDEWAYS: "neutral",
            MarketRegime.RECOVERY: "growth",
        }
        return bias_map[self]

    @classmethod
    def from_string(cls, regime: str) -> "MarketRegime":
        """
        Convert a string value to a MarketRegime enum.

        This method provides a convenient way to convert the regime string
        from the proto GetCurrentRegimeResponse message to a MarketRegime enum.

        Args:
            regime: A string value matching one of the enum values
                   ("crisis", "bear", "bull", "sideways", "recovery").

        Returns:
            MarketRegime: The corresponding market regime enum.

        Raises:
            ValueError: If regime is not a valid market regime string.

        Example:
            >>> MarketRegime.from_string("crisis")
            <MarketRegime.CRISIS: 'crisis'>
            >>> MarketRegime.from_string("bull")
            <MarketRegime.BULL: 'bull'>
            >>> MarketRegime.from_string("RECOVERY")
            <MarketRegime.RECOVERY: 'recovery'>
        """
        try:
            return cls(regime.lower())
        except ValueError:
            valid_values = [r.value for r in cls]
            raise ValueError(
                f"Invalid regime '{regime}'. Must be one of: {valid_values}"
            )
