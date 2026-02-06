"""Factor Scoring Engine for Stage 3.

Implements 6-factor scoring system with risk profile-based weighting:
- Momentum: Price trend vs moving averages
- Value: P/E, P/B ratios
- Quality: ROE, debt ratios
- Volatility: Price volatility (inverse scoring)
- Liquidity: Trading volume
- Sentiment: News/social sentiment (FinGPT with momentum fallback)
"""

import logging
import statistics
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .config import config
from .models import FactorScores, RiskProfile

if TYPE_CHECKING:
    from shared.utils.redis_client import RedisClient

    from .clients.fingpt_client import FinGPTClient
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

    def __init__(
        self,
        market_data_client: "MarketDataClient",
        fingpt_client: "FinGPTClient | None" = None,
        redis_client: "RedisClient | None" = None,
    ) -> None:
        """Initialize factor scoring engine.

        Args:
            market_data_client: Market Data Service gRPC client.
            fingpt_client: Optional FinGPT client for sentiment analysis.
            redis_client: Optional Redis client for caching sentiment results.
        """
        self.market_data = market_data_client
        self.fingpt_client = fingpt_client
        self.redis_client = redis_client

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
        """Calculate value score (0-100) based on P/E ratio.

        Lower P/E = higher score (value investing principle).

        Args:
            symbol: Stock ticker symbol

        Returns:
            Value score (0-100)
        """
        try:
            stock_info = await self.market_data.get_stock_info(symbol)

            # Check if pe_ratio is available
            if stock_info.HasField("pe_ratio"):
                pe = stock_info.pe_ratio

                # Value scoring: Lower P/E = better value
                if pe <= 0:
                    # Negative P/E means losses, return neutral
                    logger.debug(f"Negative P/E for {symbol}: {pe}, using neutral score")
                    return 50.0
                elif pe < 10:
                    return 100.0
                elif pe < 15:
                    return 80.0
                elif pe < 20:
                    return 60.0
                elif pe < 25:
                    return 40.0
                elif pe < 30:
                    return 20.0
                else:
                    return 10.0

            logger.debug(f"P/E ratio not available for {symbol}, using neutral score")
            return 50.0

        except Exception as e:
            logger.warning(f"Failed to get value score for {symbol}: {e}")
            return 50.0

    async def _calculate_quality(self, symbol: str) -> float:
        """Calculate quality score (0-100) using fundamental metrics.

        Phase 2: Uses ROE, debt/equity, and market cap for quality scoring.

        Scoring breakdown:
        - ROE weight: 40% (higher = better)
        - Debt/Equity weight: 30% (lower = better, inverse)
        - Market Cap weight: 30% (larger = better, stability)

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quality score (0-100)
        """
        try:
            stock_info = await self.market_data.get_stock_info(symbol)

            # ROE score: 0-20% ROE maps to 0-100 (higher is better)
            if stock_info.HasField("return_on_equity"):
                roe = stock_info.return_on_equity
                roe_score = min(100.0, max(0.0, roe * 500))  # 20% ROE = 100
            else:
                roe_score = 50.0  # Neutral

            # D/E score: 0-2 D/E maps to 100-0 (lower is better)
            if stock_info.HasField("debt_to_equity"):
                de = stock_info.debt_to_equity
                de_score = max(0.0, 100.0 - de * 50)  # 2.0 D/E = 0
            else:
                de_score = 50.0  # Neutral

            # Market cap score (existing logic)
            market_cap = stock_info.market_cap
            if market_cap <= 0:
                cap_score = 50.0  # Neutral for invalid
            elif market_cap >= 100_000_000_000:  # $100B+
                cap_score = min(90.0, 70.0 + (market_cap / 1_000_000_000_000) * 10)
            elif market_cap >= 10_000_000_000:  # $10B-$100B
                ratio = (market_cap - 10_000_000_000) / 90_000_000_000
                cap_score = 50.0 + ratio * 20
            else:  # <$10B
                ratio = market_cap / 10_000_000_000
                cap_score = 30.0 + ratio * 20

            # Weighted average
            final_score = roe_score * 0.4 + de_score * 0.3 + cap_score * 0.3

            logger.debug(
                f"Quality score for {symbol}: {final_score:.2f} "
                f"(ROE: {roe_score:.2f}, D/E: {de_score:.2f}, Cap: {cap_score:.2f})"
            )
            return final_score

        except Exception as e:
            logger.warning(f"Failed to get quality score for {symbol}: {e}")
            return 50.0

    async def _calculate_sentiment(self, symbol: str) -> float:
        """Calculate sentiment score (0-100) using FinGPT analysis.

        Uses FinGPT for news sentiment analysis with Redis caching (1 hour TTL).
        Falls back to momentum proxy if FinGPT is unavailable or low confidence.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            Sentiment score (0-100).
        """
        # Try cached sentiment first
        cached_score = await self._get_cached_sentiment(symbol)
        if cached_score is not None:
            logger.debug(f"Using cached sentiment for {symbol}: {cached_score:.2f}")
            return cached_score

        # Try FinGPT if available
        if self.fingpt_client:
            try:
                result = await self.fingpt_client.analyze_sentiment(symbol)

                if result["confidence"] > 0.5:  # Only use if confident
                    # Convert -1.0 ~ 1.0 to 0-100 scale
                    sentiment = result["sentiment"]
                    score = (sentiment + 1.0) * 50.0
                    score = max(0.0, min(100.0, score))

                    logger.debug(
                        f"FinGPT sentiment for {symbol}: {score:.2f} "
                        f"(raw: {sentiment}, confidence: {result['confidence']})"
                    )

                    # Cache the result
                    await self._cache_sentiment(symbol, score)
                    return score

                logger.debug(
                    f"FinGPT low confidence for {symbol} "
                    f"({result['confidence']:.2f}), using momentum proxy"
                )

            except Exception as e:
                logger.warning(f"FinGPT failed for {symbol}: {e}, using momentum proxy")

        # Fallback to momentum proxy
        return await self._calculate_sentiment_from_momentum(symbol)

    async def _calculate_sentiment_from_momentum(self, symbol: str) -> float:
        """Calculate sentiment using momentum as proxy (fallback).

        Uses price momentum as a simplified sentiment proxy.
        - High momentum (>70): Bullish sentiment (60-80)
        - Low momentum (<30): Bearish sentiment (20-40)
        - Neutral momentum: Neutral sentiment (40-60)

        Args:
            symbol: Stock ticker symbol.

        Returns:
            Sentiment score (0-100).
        """
        try:
            ohlcv_bars = await self.market_data.get_ohlcv(symbol, period="3mo", interval="1d")
            momentum = self._calculate_momentum(ohlcv_bars)

            if momentum > 70:
                # Map momentum 70-100 to sentiment 60-80
                score = 60.0 + (momentum - 70) * (20.0 / 30.0)
            elif momentum < 30:
                # Map momentum 0-30 to sentiment 20-40
                score = 20.0 + momentum * (20.0 / 30.0)
            else:
                # Map momentum 30-70 to sentiment 40-60
                score = 40.0 + (momentum - 30) * (20.0 / 40.0)

            logger.debug(
                f"Sentiment (momentum proxy) for {symbol}: {score:.2f} (momentum: {momentum:.2f})"
            )
            return score

        except Exception as e:
            logger.warning(f"Failed to get sentiment score for {symbol}: {e}")
            return 50.0

    async def _get_cached_sentiment(self, symbol: str) -> float | None:
        """Get cached sentiment score from Redis.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            Cached sentiment score or None if not cached.
        """
        if not self.redis_client:
            return None

        try:
            cache_key = f"sentiment:{symbol}"
            cached: Any = await self.redis_client.get(cache_key)

            if cached is not None:
                return float(cached)
            return None

        except Exception as e:
            logger.warning(f"Failed to get cached sentiment for {symbol}: {e}")
            return None

    async def _cache_sentiment(self, symbol: str, score: float) -> None:
        """Cache sentiment score in Redis.

        Args:
            symbol: Stock ticker symbol.
            score: Sentiment score to cache.
        """
        if not self.redis_client:
            return

        try:
            cache_key = f"sentiment:{symbol}"
            await self.redis_client.setex(cache_key, config.sentiment_cache_ttl, score)
            logger.debug(
                f"Cached sentiment for {symbol}: {score:.2f} (TTL: {config.sentiment_cache_ttl}s)"
            )

        except Exception as e:
            logger.warning(f"Failed to cache sentiment for {symbol}: {e}")
