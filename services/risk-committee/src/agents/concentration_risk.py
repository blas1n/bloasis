"""Concentration Risk Agent - Checks portfolio concentration."""

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from ..config import config
from ..models import OrderRequest, Portfolio, RiskDecision, RiskVote

if TYPE_CHECKING:
    from shared.utils.redis_client import RedisClient

    from ..clients.market_data_client import MarketDataClient
    from ..clients.portfolio_client import PortfolioClient

logger = logging.getLogger(__name__)

# Cache TTL for sector data (24 hours)
SECTOR_CACHE_TTL = 86400


class ConcentrationRiskAgent:
    """Evaluates portfolio concentration risk.

    Checks:
    - Sector concentration
    - Correlated assets
    - Industry overlap
    """

    # Correlation between sectors (simplified)
    SECTOR_CORRELATIONS = {
        ("Technology", "Consumer Discretionary"): 0.7,
        ("Financials", "Energy"): 0.5,
        ("Healthcare", "Consumer Staples"): 0.4,
    }

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
        if correlation_risk > 0.8:
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
        """Check correlation of symbol with existing positions.

        Args:
            symbol: Symbol to check
            portfolio: Current portfolio

        Returns:
            Maximum correlation score (0.0 - 1.0)
        """
        new_sector = await self._get_sector(symbol)
        max_correlation = 0.0

        for position in portfolio.positions:
            position_sector = await self._get_sector(position.symbol)
            # Fallback to position's sector if MarketDataService returns Unknown
            if position_sector == "Unknown" and position.sector:
                position_sector = position.sector

            # Same sector = high correlation
            if position_sector == new_sector:
                max_correlation = max(max_correlation, 0.9)
            else:
                # Check cross-sector correlation
                pair1 = (new_sector, position_sector)
                pair2 = (position_sector, new_sector)
                corr = self.SECTOR_CORRELATIONS.get(pair1, self.SECTOR_CORRELATIONS.get(pair2, 0.0))
                max_correlation = max(max_correlation, corr)

        return max_correlation
