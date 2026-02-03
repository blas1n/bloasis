"""Factor Scoring Engine for Stage 3.

Implements 6-factor scoring system with risk profile-based weighting:
- Momentum: Price trend vs moving averages
- Value: P/E, P/B ratios
- Quality: ROE, debt ratios
- Volatility: Price volatility (inverse scoring)
- Liquidity: Trading volume
- Sentiment: News/social sentiment
"""

import logging
import statistics
from decimal import Decimal
from typing import TYPE_CHECKING

from .models import FactorScores, RiskProfile

if TYPE_CHECKING:
    from .clients.market_data_client import MarketDataClient

logger = logging.getLogger(__name__)

# Factor weights by Risk Profile
FACTOR_WEIGHTS: dict[RiskProfile, dict[str, float]] = {
    RiskProfile.CONSERVATIVE: {
        "momentum": 0.10,
        "value": 0.25,
        "quality": 0.30,
        "volatility": 0.20,  # Low volatility preferred
        "liquidity": 0.10,
        "sentiment": 0.05,
    },
    RiskProfile.MODERATE: {
        "momentum": 0.20,
        "value": 0.20,
        "quality": 0.20,
        "volatility": 0.15,
        "liquidity": 0.10,
        "sentiment": 0.15,
    },
    RiskProfile.AGGRESSIVE: {
        "momentum": 0.30,
        "value": 0.10,
        "quality": 0.15,
        "volatility": 0.05,  # Higher volatility acceptable
        "liquidity": 0.10,
        "sentiment": 0.30,
    },
}


class FactorScoringEngine:
    """Factor scoring engine for stock evaluation."""

    def __init__(self, market_data_client: "MarketDataClient"):
        """Initialize factor scoring engine.

        Args:
            market_data_client: Market Data Service gRPC client
        """
        self.market_data = market_data_client

    async def calculate_factor_scores(self, symbol: str, regime: str) -> FactorScores:
        """Calculate all 6 factor scores for a symbol.

        Args:
            symbol: Stock ticker symbol
            regime: Current market regime (for context)

        Returns:
            FactorScores with all 6 factors calculated
        """
        logger.info(f"Calculating factor scores for {symbol} in {regime} regime")

        # Fetch OHLCV data (3 months for sufficient history)
        ohlcv_bars = await self.market_data.get_ohlcv(symbol, period="3mo", interval="1d")

        # Calculate each factor
        momentum = self._calculate_momentum(ohlcv_bars)
        value = await self._calculate_value(symbol)
        quality = await self._calculate_quality(symbol)
        volatility = self._calculate_volatility(ohlcv_bars)
        liquidity = self._calculate_liquidity(ohlcv_bars)
        sentiment = await self._calculate_sentiment(symbol)

        return FactorScores(
            momentum=momentum,
            value=value,
            quality=quality,
            volatility=volatility,
            liquidity=liquidity,
            sentiment=sentiment,
        )

    def calculate_final_score(
        self, factor_scores: FactorScores, risk_profile: RiskProfile
    ) -> Decimal:
        """Calculate weighted final score based on risk profile.

        Args:
            factor_scores: Individual factor scores
            risk_profile: User's risk profile (determines weights)

        Returns:
            Final weighted score (0-100) as Decimal
        """
        weights = FACTOR_WEIGHTS[risk_profile]

        # Calculate weighted sum using Decimal for precision
        score = (
            Decimal(str(factor_scores.momentum)) * Decimal(str(weights["momentum"]))
            + Decimal(str(factor_scores.value)) * Decimal(str(weights["value"]))
            + Decimal(str(factor_scores.quality)) * Decimal(str(weights["quality"]))
            + Decimal(str(factor_scores.volatility)) * Decimal(str(weights["volatility"]))
            + Decimal(str(factor_scores.liquidity)) * Decimal(str(weights["liquidity"]))
            + Decimal(str(factor_scores.sentiment)) * Decimal(str(weights["sentiment"]))
        )

        # Round to 2 decimal places
        return score.quantize(Decimal("0.01"))

    def _calculate_momentum(self, ohlcv_bars: list[dict]) -> float:
        """Calculate momentum score (0-100).

        Based on price position relative to 20-day moving average.

        Args:
            ohlcv_bars: OHLCV data bars

        Returns:
            Momentum score (0-100)
        """
        if len(ohlcv_bars) < 20:
            logger.warning(f"Insufficient data for momentum calculation: {len(ohlcv_bars)} bars")
            return 50.0

        recent_close = ohlcv_bars[-1]["close"]
        ma20 = sum(bar["close"] for bar in ohlcv_bars[-20:]) / 20

        # Calculate % above/below MA20
        momentum_pct = ((recent_close - ma20) / ma20) * 100

        # Convert to 0-100 scale (centered at 50)
        # +10% above MA20 = 100, -10% below = 0
        score = max(0, min(100, 50 + (momentum_pct * 5)))

        logger.debug(f"Momentum: {score:.2f} (price: {recent_close:.2f}, MA20: {ma20:.2f})")
        return score

    def _calculate_volatility(self, ohlcv_bars: list[dict]) -> float:
        """Calculate volatility score (0-100).

        Inverse scoring: Lower volatility = higher score.
        Based on annualized standard deviation of returns.

        Args:
            ohlcv_bars: OHLCV data bars

        Returns:
            Volatility score (0-100, inverse)
        """
        if len(ohlcv_bars) < 20:
            logger.warning(f"Insufficient data for volatility calculation: {len(ohlcv_bars)} bars")
            return 50.0

        # Calculate daily returns
        returns = [
            (ohlcv_bars[i]["close"] - ohlcv_bars[i - 1]["close"]) / ohlcv_bars[i - 1]["close"]
            for i in range(1, len(ohlcv_bars))
        ]

        # Annualized standard deviation (252 trading days)
        std_dev = statistics.stdev(returns) * (252**0.5)

        # Convert to score: 20% volatility = 0, 0% = 100
        # Inverse: lower volatility = higher score
        score = max(0, 100 - (std_dev * 500))

        logger.debug(f"Volatility: {score:.2f} (annualized std: {std_dev:.2%})")
        return score

    def _calculate_liquidity(self, ohlcv_bars: list[dict]) -> float:
        """Calculate liquidity score (0-100).

        Based on average daily volume.

        Args:
            ohlcv_bars: OHLCV data bars

        Returns:
            Liquidity score (0-100)
        """
        if len(ohlcv_bars) < 20:
            logger.warning(f"Insufficient data for liquidity calculation: {len(ohlcv_bars)} bars")
            return 50.0

        # Average volume over 20 days
        avg_volume = sum(bar["volume"] for bar in ohlcv_bars[-20:]) / 20

        # Convert to score: 1M+ volume = 100
        score = min(100, (avg_volume / 1_000_000) * 100)

        logger.debug(f"Liquidity: {score:.2f} (avg volume: {avg_volume:,.0f})")
        return score

    async def _calculate_value(self, symbol: str) -> float:
        """Calculate value score (0-100).

        Based on P/E and P/B ratios (lower = better value).
        TODO: Integrate with financial data API.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Value score (0-100)
        """
        # TODO: Implement with financial data API (Alpha Vantage, yfinance)
        # For now, return neutral score
        logger.debug(f"Value score placeholder for {symbol}: 50.0")
        return 50.0

    async def _calculate_quality(self, symbol: str) -> float:
        """Calculate quality score (0-100).

        Based on ROE, debt/equity ratios.
        TODO: Integrate with financial data API.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quality score (0-100)
        """
        # TODO: Implement with financial data API
        # For now, return neutral score
        logger.debug(f"Quality score placeholder for {symbol}: 50.0")
        return 50.0

    async def _calculate_sentiment(self, symbol: str) -> float:
        """Calculate sentiment score (0-100).

        Based on news and social media sentiment.
        TODO: Integrate with FinGPT sentiment analysis.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Sentiment score (0-100)
        """
        # TODO: Implement with FinGPT sentiment API
        # For now, return neutral score
        logger.debug(f"Sentiment score placeholder for {symbol}: 50.0")
        return 50.0
