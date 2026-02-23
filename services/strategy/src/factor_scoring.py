"""Factor Scoring Engine for Stage 3.

Implements 6-factor scoring system with risk profile-based weighting:
- Momentum: Price trend vs moving averages
- Value: P/E, P/B ratios
- Quality: ROE, debt ratios
- Volatility: Price volatility (inverse scoring)
- Liquidity: Trading volume
- Sentiment: Price momentum proxy
"""

import logging
import math
import statistics
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .config import config
from .models import FactorScores, RiskProfile

if TYPE_CHECKING:
    from shared.utils.redis_client import RedisClient

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


# Regime-adaptive factor multipliers
# Adjusts base weights per market regime to emphasize appropriate factors
REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "crisis": {
        "momentum": 0.3,
        "value": 1.5,
        "quality": 1.8,
        "volatility": 2.0,
        "liquidity": 1.0,
        "sentiment": 0.2,
    },
    "severe_bear": {
        "momentum": 0.5,
        "value": 1.3,
        "quality": 1.5,
        "volatility": 1.5,
        "liquidity": 1.0,
        "sentiment": 0.5,
    },
    "mild_bear": {
        "momentum": 0.7,
        "value": 1.2,
        "quality": 1.2,
        "volatility": 1.2,
        "liquidity": 1.0,
        "sentiment": 0.7,
    },
    "sideways": {
        "momentum": 0.8,
        "value": 1.2,
        "quality": 1.0,
        "volatility": 1.0,
        "liquidity": 1.0,
        "sentiment": 0.8,
    },
    "recovery": {
        "momentum": 1.5,
        "value": 1.2,
        "quality": 0.8,
        "volatility": 0.7,
        "liquidity": 1.0,
        "sentiment": 1.3,
    },
    "normal_bull": {
        "momentum": 1.2,
        "value": 0.8,
        "quality": 0.9,
        "volatility": 0.7,
        "liquidity": 1.0,
        "sentiment": 1.2,
    },
    "strong_bull": {
        "momentum": 1.3,
        "value": 0.7,
        "quality": 0.8,
        "volatility": 0.6,
        "liquidity": 1.0,
        "sentiment": 1.3,
    },
}


class FactorScoringEngine:
    """Factor scoring engine for stock evaluation."""

    def __init__(
        self,
        market_data_client: "MarketDataClient",
        redis_client: "RedisClient | None" = None,
    ) -> None:
        """Initialize factor scoring engine.

        Args:
            market_data_client: Market Data Service gRPC client.
            redis_client: Optional Redis client for caching sentiment results.
        """
        self.market_data = market_data_client
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
        self,
        factor_scores: FactorScores,
        risk_profile: RiskProfile,
        regime: str = "normal_bull",
    ) -> Decimal:
        """Calculate weighted final score based on risk profile and market regime.

        Applies regime-adaptive multipliers to base weights, then normalizes
        so weights sum to 1.0.

        Args:
            factor_scores: Individual factor scores
            risk_profile: User's risk profile (determines base weights)
            regime: Current market regime (adjusts weight emphasis)

        Returns:
            Final weighted score (0-100) as Decimal
        """
        base_weights = FACTOR_WEIGHTS[risk_profile]
        regime_mults = REGIME_MULTIPLIERS.get(regime, {})

        # Apply regime multipliers to base weights
        adjusted: dict[str, float] = {}
        for factor, base_w in base_weights.items():
            mult = regime_mults.get(factor, 1.0)
            adjusted[factor] = base_w * mult

        # Normalize so weights sum to 1.0
        total = sum(adjusted.values())
        if total > 0:
            weights = {k: v / total for k, v in adjusted.items()}
        else:
            weights = base_weights

        # Calculate weighted sum using Decimal for precision
        score = (
            Decimal(str(factor_scores.momentum)) * Decimal(str(weights["momentum"]))
            + Decimal(str(factor_scores.value)) * Decimal(str(weights["value"]))
            + Decimal(str(factor_scores.quality)) * Decimal(str(weights["quality"]))
            + Decimal(str(factor_scores.volatility))
            * Decimal(str(weights["volatility"]))
            + Decimal(str(factor_scores.liquidity))
            * Decimal(str(weights["liquidity"]))
            + Decimal(str(factor_scores.sentiment))
            * Decimal(str(weights["sentiment"]))
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
        """Calculate value score (0-100) using 3-indicator continuous scoring.

        Scoring breakdown:
        - P/E ratio (40%): Continuous bell-curve peaking at PE=12
        - Profit Margin (30%): Higher margin = better value
        - Current Ratio (30%): Healthy balance sheet (peak at 1.5-2.0)

        Args:
            symbol: Stock ticker symbol

        Returns:
            Value score (0-100)
        """
        try:
            stock_info = await self.market_data.get_stock_info(symbol)

            # P/E score (40%) — continuous bell curve, peak at PE=12
            if stock_info.HasField("pe_ratio"):
                pe = stock_info.pe_ratio
                if pe <= 0:
                    pe_score = 30.0  # Negative earnings → below neutral
                else:
                    # Gaussian-like: score = 100 * exp(-((pe - 12) / 10)^2)
                    pe_score = 100.0 * math.exp(-((pe - 12) / 10) ** 2)
            else:
                pe_score = 50.0

            # Profit Margin score (30%) — 0% → 0, 20%+ → 100
            if stock_info.HasField("profit_margin"):
                pm = stock_info.profit_margin
                if pm < 0:
                    pm_score = max(0.0, 20.0 + pm * 100)  # Slightly penalize losses
                else:
                    pm_score = min(100.0, pm * 500)  # 20% margin = 100
            else:
                pm_score = 50.0

            # Current Ratio score (30%) — peak at 1.5-2.0
            if stock_info.HasField("current_ratio"):
                cr = stock_info.current_ratio
                if cr <= 0:
                    cr_score = 0.0
                elif cr < 1.0:
                    cr_score = cr * 50.0  # Below 1.0 is weak
                elif cr <= 2.0:
                    cr_score = 50.0 + (cr - 1.0) * 50.0  # 1.0-2.0 → 50-100
                else:
                    # >2.0 starts declining (idle assets)
                    cr_score = max(40.0, 100.0 - (cr - 2.0) * 15.0)
            else:
                cr_score = 50.0

            final_score = pe_score * 0.4 + pm_score * 0.3 + cr_score * 0.3

            logger.debug(
                f"Value score for {symbol}: {final_score:.2f} "
                f"(PE: {pe_score:.2f}, PM: {pm_score:.2f}, CR: {cr_score:.2f})"
            )
            return final_score

        except Exception as e:
            logger.warning(f"Failed to get value score for {symbol}: {e}")
            return 50.0

    async def _calculate_quality(self, symbol: str) -> float:
        """Calculate quality score (0-100) using 5 fundamental metrics.

        Scoring breakdown:
        - ROE (25%): Higher = better profitability
        - D/E (20%): Lower = better financial health (inverse)
        - Profit Margin (25%): Higher = better operational efficiency
        - Current Ratio (15%): Healthy liquidity (peak at 1.5-2.0)
        - Market Cap (15%): Larger = more stability

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quality score (0-100)
        """
        try:
            stock_info = await self.market_data.get_stock_info(symbol)

            # ROE score (25%): 0-25% ROE maps to 0-100
            if stock_info.HasField("return_on_equity"):
                roe = stock_info.return_on_equity
                if roe < 0:
                    roe_score = max(0.0, 20.0 + roe * 100)
                else:
                    roe_score = min(100.0, roe * 400)  # 25% ROE = 100
            else:
                roe_score = 50.0

            # D/E score (20%): 0-2 D/E maps to 100-0 (lower is better)
            if stock_info.HasField("debt_to_equity"):
                de = stock_info.debt_to_equity
                de_score = max(0.0, 100.0 - de * 50)  # 2.0 D/E = 0
            else:
                de_score = 50.0

            # Profit Margin score (25%): 0-25% maps to 0-100
            if stock_info.HasField("profit_margin"):
                pm = stock_info.profit_margin
                if pm < 0:
                    pm_score = max(0.0, 20.0 + pm * 100)
                else:
                    pm_score = min(100.0, pm * 400)  # 25% margin = 100
            else:
                pm_score = 50.0

            # Current Ratio score (15%): peak at 1.5-2.0
            if stock_info.HasField("current_ratio"):
                cr = stock_info.current_ratio
                if cr <= 0:
                    cr_score = 0.0
                elif cr < 1.0:
                    cr_score = cr * 50.0
                elif cr <= 2.0:
                    cr_score = 50.0 + (cr - 1.0) * 50.0
                else:
                    cr_score = max(40.0, 100.0 - (cr - 2.0) * 15.0)
            else:
                cr_score = 50.0

            # Market Cap score (15%): logarithmic scale
            market_cap = stock_info.market_cap
            if market_cap <= 0:
                cap_score = 50.0
            elif market_cap >= 100_000_000_000:  # $100B+
                cap_score = min(
                    90.0,
                    70.0 + (market_cap / 1_000_000_000_000) * 10,
                )
            elif market_cap >= 10_000_000_000:  # $10B-$100B
                ratio = (market_cap - 10_000_000_000) / 90_000_000_000
                cap_score = 50.0 + ratio * 20
            else:  # <$10B
                ratio = market_cap / 10_000_000_000
                cap_score = 30.0 + ratio * 20

            final_score = (
                roe_score * 0.25
                + de_score * 0.20
                + pm_score * 0.25
                + cr_score * 0.15
                + cap_score * 0.15
            )

            logger.debug(
                f"Quality score for {symbol}: {final_score:.2f} "
                f"(ROE: {roe_score:.2f}, D/E: {de_score:.2f}, "
                f"PM: {pm_score:.2f}, CR: {cr_score:.2f}, "
                f"Cap: {cap_score:.2f})"
            )
            return final_score

        except Exception as e:
            logger.warning(f"Failed to get quality score for {symbol}: {e}")
            return 50.0

    async def _calculate_sentiment(self, symbol: str) -> float:
        """Calculate sentiment score (0-100) using momentum proxy.

        Uses price momentum as a simplified sentiment proxy with Redis caching.

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
