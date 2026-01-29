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
    - "normal_bear": Declining market, moderate volatility
    - "normal_bull": Rising market, low-moderate volatility
    - "euphoria": Extreme optimism, potential bubble conditions
    - "high_volatility": Elevated VIX without clear direction
    - "low_volatility": Unusually calm markets, potential complacency

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
        - Crisis/High Volatility -> Defensive sectors (utilities, healthcare, consumer staples)
        - Bear markets -> Balanced defensive with some value plays
        - Bull markets -> Balanced growth with cyclical exposure
        - Euphoria -> Speculative with momentum and growth focus
        - Low Volatility -> Growth-oriented with higher risk tolerance

    Attributes:
        CRISIS: Crisis regime - High volatility, risk-off conditions.
        NORMAL_BEAR: Normal bear regime - Declining market with moderate volatility.
        NORMAL_BULL: Normal bull regime - Rising market with low-moderate volatility.
        EUPHORIA: Euphoria regime - Extreme optimism, potential bubble.
        HIGH_VOLATILITY: High volatility regime - Elevated VIX without clear direction.
        LOW_VOLATILITY: Low volatility regime - Unusually calm markets.

    Example:
        >>> regime = MarketRegime.NORMAL_BULL
        >>> regime.value
        'normal_bull'
        >>> bias = regime.get_sector_bias()
        >>> bias
        'balanced_growth'
        >>> MarketRegime.from_string("crisis")
        <MarketRegime.CRISIS: 'crisis'>
    """

    CRISIS = "crisis"
    NORMAL_BEAR = "normal_bear"
    NORMAL_BULL = "normal_bull"
    EUPHORIA = "euphoria"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"

    def get_sector_bias(self) -> str:
        """
        Convert MarketRegime to a sector bias string.

        Maps each market regime to a recommended sector allocation strategy:
        - CRISIS -> "defensive": Focus on utilities, healthcare, consumer staples
        - NORMAL_BEAR -> "balanced_defensive": Mix of defensive with value opportunities
        - NORMAL_BULL -> "balanced_growth": Blend of growth and cyclical sectors
        - EUPHORIA -> "speculative": Momentum-driven, growth-heavy allocation
        - HIGH_VOLATILITY -> "defensive": Similar to crisis, reduce risk exposure
        - LOW_VOLATILITY -> "growth": Favor growth and technology sectors

        Returns:
            str: Sector bias string for Tier 2 strategy generation.

        Example:
            >>> MarketRegime.CRISIS.get_sector_bias()
            'defensive'
            >>> MarketRegime.NORMAL_BEAR.get_sector_bias()
            'balanced_defensive'
            >>> MarketRegime.NORMAL_BULL.get_sector_bias()
            'balanced_growth'
            >>> MarketRegime.EUPHORIA.get_sector_bias()
            'speculative'
            >>> MarketRegime.HIGH_VOLATILITY.get_sector_bias()
            'defensive'
            >>> MarketRegime.LOW_VOLATILITY.get_sector_bias()
            'growth'
        """
        bias_map: dict[MarketRegime, str] = {
            MarketRegime.CRISIS: "defensive",
            MarketRegime.NORMAL_BEAR: "balanced_defensive",
            MarketRegime.NORMAL_BULL: "balanced_growth",
            MarketRegime.EUPHORIA: "speculative",
            MarketRegime.HIGH_VOLATILITY: "defensive",
            MarketRegime.LOW_VOLATILITY: "growth",
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
                   ("crisis", "normal_bear", "normal_bull", "euphoria",
                    "high_volatility", "low_volatility").

        Returns:
            MarketRegime: The corresponding market regime enum.

        Raises:
            ValueError: If regime is not a valid market regime string.

        Example:
            >>> MarketRegime.from_string("crisis")
            <MarketRegime.CRISIS: 'crisis'>
            >>> MarketRegime.from_string("normal_bull")
            <MarketRegime.NORMAL_BULL: 'normal_bull'>
            >>> MarketRegime.from_string("EUPHORIA")
            <MarketRegime.EUPHORIA: 'euphoria'>
        """
        try:
            return cls(regime.lower())
        except ValueError:
            valid_values = [r.value for r in cls]
            raise ValueError(
                f"Invalid regime '{regime}'. Must be one of: {valid_values}"
            )
