"""Concentration Risk Agent - Checks portfolio concentration."""

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np

from ..config import config
from ..models import OrderRequest, Portfolio, RiskDecision, RiskVote

if TYPE_CHECKING:
    from shared.utils.redis_client import RedisClient

    from ..clients.market_data_client import MarketDataClient
    from ..clients.portfolio_client import PortfolioClient

logger = logging.getLogger(__name__)

# Cache TTL for sector data (24 hours)
SECTOR_CACHE_TTL = 86400

# Minimum data points for reliable correlation
_MIN_CORRELATION_BARS = 30

# Correlation threshold for position reduction
_HIGH_CORRELATION_THRESHOLD = 0.7


class ConcentrationRiskAgent:
    """Evaluates portfolio concentration risk.

    Checks:
    - Sector concentration
    - Return-based correlation between assets
    """

    def __init__(
        self,
        portfolio_client: "PortfolioClient",
        market_data_client: "MarketDataClient | None" = None,
        redis_client: "RedisClient | None" = None,
    ) -> None:
        """Initialize Concentration Risk Agent.

        Args:
            portfolio_client: Client for Portfolio Service
            market_data_client: Client for Market Data Service (optional)
            redis_client: Redis client for caching (optional)
        """
        self.portfolio = portfolio_client
        self.market_data = market_data_client
        self.redis = redis_client
        self.max_sector_concentration = Decimal(str(config.default_max_sector_concentration))
        self.max_correlation_exposure = Decimal("0.50")

    async def evaluate(self, order: OrderRequest, portfolio: Portfolio) -> RiskVote:
        """Evaluate concentration risk.

        Args:
            order: Order to evaluate
            portfolio: Current portfolio state

        Returns:
            Risk vote with decision and reasoning
        """
        portfolio_value = Decimal(str(portfolio.total_value))

        if portfolio_value == 0:
            return RiskVote(
                agent="ConcentrationRiskAgent",
                decision=RiskDecision.APPROVE,
                risk_score=0.0,
                reasoning="Empty portfolio - no concentration risk",
            )

        # Get sector of the ordered symbol
        sector = await self._get_sector(order.symbol)

        # Calculate sector concentration after order
        sector_exposure = await self._calculate_sector_exposure(portfolio, sector)
        order_value = Decimal(str(order.size)) * Decimal(str(order.price))

        # For sell orders, reduce sector exposure
        if order.action.lower() == "sell":
            new_sector_value = sector_exposure - order_value
        else:
            new_sector_value = sector_exposure + order_value

        new_sector_pct = new_sector_value / portfolio_value

        if new_sector_pct > self.max_sector_concentration:
            return RiskVote(
                agent="ConcentrationRiskAgent",
                decision=RiskDecision.ADJUST,
                risk_score=0.7,
                reasoning=(
                    f"Sector {sector} concentration {float(new_sector_pct):.1%} "
                    f"exceeds limit {float(self.max_sector_concentration):.1%}"
                ),
                adjustments=[
                    {
                        "type": "reduce_sector",
                        "sector": sector,
                        "max_pct": float(self.max_sector_concentration),
                        "reason": "sector_concentration",
                    }
                ],
            )

        # Check correlation with existing positions
        correlation_risk = await self._check_correlation(order.symbol, portfolio)
        if correlation_risk > _HIGH_CORRELATION_THRESHOLD:
            return RiskVote(
                agent="ConcentrationRiskAgent",
                decision=RiskDecision.ADJUST,
                risk_score=correlation_risk,
                reasoning="High correlation with existing positions",
                adjustments=[
                    {
                        "type": "reduce_size",
                        "reason": "correlation",
                        "value": 0.5,  # Reduce by 50%
                    }
                ],
            )

        # Calculate risk score based on sector concentration
        risk_score = float(new_sector_pct / self.max_sector_concentration)

        return RiskVote(
            agent="ConcentrationRiskAgent",
            decision=RiskDecision.APPROVE,
            risk_score=min(risk_score, 1.0),
            reasoning="Concentration within limits",
        )

    async def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol from Market Data Service.

        Uses Redis caching with 24-hour TTL to minimize API calls.
        Falls back to "Unknown" if MarketDataService is unavailable.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Sector name or "Unknown" if unavailable
        """
        # Check cache first
        cache_key = f"sector:{symbol}"

        if self.redis:
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    return str(cached)
            except Exception as e:
                logger.warning(f"Redis cache read error for {symbol}: {e}")

        # Fetch from Market Data Service
        if self.market_data:
            try:
                stock_info = await self.market_data.get_stock_info(symbol)
                sector = stock_info.sector if stock_info.sector else "Unknown"

                # Cache for 24 hours
                if self.redis:
                    try:
                        await self.redis.setex(cache_key, SECTOR_CACHE_TTL, sector)
                    except Exception as e:
                        logger.warning(f"Redis cache write error for {symbol}: {e}")

                return sector

            except Exception as e:
                logger.warning(f"Failed to get sector for {symbol}: {e}")

        return "Unknown"

    async def _calculate_sector_exposure(self, portfolio: Portfolio, sector: str) -> Decimal:
        """Calculate total exposure to a sector.

        Args:
            portfolio: Current portfolio
            sector: Sector name

        Returns:
            Total sector exposure value
        """
        total = Decimal("0")
        for position in portfolio.positions:
            position_sector = await self._get_sector(position.symbol)
            # Fallback to position's sector if MarketDataService returns Unknown
            if position_sector == "Unknown" and position.sector:
                position_sector = position.sector
            if position_sector == sector:
                total += Decimal(str(position.market_value))
        return total

    async def _check_correlation(self, symbol: str, portfolio: Portfolio) -> float:
        """Check return-based correlation of symbol with existing positions.

        Uses 60-day daily returns and Pearson correlation.
        Falls back to sector-based heuristic when market data is unavailable.

        Args:
            symbol: Symbol to check
            portfolio: Current portfolio

        Returns:
            Maximum absolute correlation (0.0 - 1.0)
        """
        if not portfolio.positions:
            return 0.0

        # Fetch closes for the new symbol
        new_closes = await self._get_closes(symbol)
        max_correlation = 0.0

        for position in portfolio.positions:
            if position.symbol == symbol:
                continue

            pos_closes = await self._get_closes(position.symbol)

            # Compute Pearson correlation on daily returns
            corr = self._pearson_correlation(new_closes, pos_closes)
            if corr is not None:
                max_correlation = max(max_correlation, abs(corr))
            else:
                # Fallback: same sector → assume 0.6 correlation
                new_sector = await self._get_sector(symbol)
                pos_sector = await self._get_sector(position.symbol)
                if pos_sector == "Unknown" and position.sector:
                    pos_sector = position.sector
                if new_sector == pos_sector and new_sector != "Unknown":
                    max_correlation = max(max_correlation, 0.6)

        return max_correlation

    async def _get_closes(self, symbol: str) -> list[float]:
        """Fetch closing prices via MarketDataClient.

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of closing prices, or empty list on failure.
        """
        if not self.market_data:
            return []
        try:
            return await self.market_data.get_ohlcv_closes(symbol, days=60)
        except Exception as e:
            logger.warning(f"Failed to get closes for {symbol}: {e}")
            return []

    @staticmethod
    def _pearson_correlation(closes_a: list[float], closes_b: list[float]) -> float | None:
        """Compute Pearson correlation on daily returns.

        Args:
            closes_a: Closing prices for asset A
            closes_b: Closing prices for asset B

        Returns:
            Correlation coefficient, or None if insufficient data.
        """
        # Align lengths (use shorter series)
        min_len = min(len(closes_a), len(closes_b))
        if min_len < _MIN_CORRELATION_BARS + 1:
            return None

        a = np.array(closes_a[-min_len:])
        b = np.array(closes_b[-min_len:])

        # Daily returns
        ret_a = np.diff(a) / a[:-1]
        ret_b = np.diff(b) / b[:-1]

        # Guard against constant series
        if np.std(ret_a) == 0 or np.std(ret_b) == 0:
            return None

        corr_matrix = np.corrcoef(ret_a, ret_b)
        return float(corr_matrix[0, 1])
