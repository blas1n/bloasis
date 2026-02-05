"""Concentration Risk Agent - Checks portfolio concentration."""

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from ..config import config
from ..models import OrderRequest, Portfolio, RiskDecision, RiskVote

if TYPE_CHECKING:
    from ..clients.portfolio_client import PortfolioClient

logger = logging.getLogger(__name__)

# TODO: Replace with Market Data Service API call (GetSymbolInfo RPC)
# Temporary hardcoded sector mapping until Market Data Service provides sector information
SYMBOL_SECTORS = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "GOOGL": "Technology",
    "AMZN": "Consumer Discretionary",
    "META": "Technology",
    "NVDA": "Technology",
    "TSLA": "Consumer Discretionary",
    "JPM": "Financials",
    "V": "Financials",
    "JNJ": "Healthcare",
    "UNH": "Healthcare",
    "PG": "Consumer Staples",
    "XOM": "Energy",
    "CVX": "Energy",
}


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

    def __init__(self, portfolio_client: "PortfolioClient") -> None:
        """Initialize Concentration Risk Agent.

        Args:
            portfolio_client: Client for Portfolio Service
        """
        self.portfolio = portfolio_client
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
        sector_exposure = self._calculate_sector_exposure(portfolio, sector)
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
        """Get sector for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Sector name
        """
        return SYMBOL_SECTORS.get(symbol, "Unknown")

    def _calculate_sector_exposure(self, portfolio: Portfolio, sector: str) -> Decimal:
        """Calculate total exposure to a sector.

        Args:
            portfolio: Current portfolio
            sector: Sector name

        Returns:
            Total sector exposure value
        """
        total = Decimal("0")
        for position in portfolio.positions:
            position_sector = SYMBOL_SECTORS.get(position.symbol, position.sector)
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
            position_sector = SYMBOL_SECTORS.get(position.symbol, position.sector)

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
