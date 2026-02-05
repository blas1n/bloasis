"""Market Risk Agent - Checks market conditions."""

import logging
from typing import TYPE_CHECKING

from ..config import config
from ..models import OrderRequest, Portfolio, RiskDecision, RiskVote

if TYPE_CHECKING:
    from ..clients.market_data_client import MarketDataClient

logger = logging.getLogger(__name__)


class MarketRiskAgent:
    """Evaluates market condition risk.

    Checks:
    - VIX level (volatility)
    - Market regime
    - Liquidity conditions
    """

    # Liquidity thresholds
    LIQUIDITY_LOW_THRESHOLD = 0.5
    MIN_DAILY_VOLUME = 1_000_000  # Minimum average daily volume

    def __init__(self, market_data_client: "MarketDataClient") -> None:
        """Initialize Market Risk Agent.

        Args:
            market_data_client: Client for Market Data Service
        """
        self.market_data = market_data_client
        self.vix_high_threshold = config.vix_high_threshold
        self.vix_extreme_threshold = config.vix_extreme_threshold

    async def evaluate(self, order: OrderRequest, portfolio: Portfolio) -> RiskVote:
        """Evaluate market risk.

        Args:
            order: Order to evaluate
            portfolio: Current portfolio state

        Returns:
            Risk vote with decision and reasoning
        """
        # Get current VIX
        vix = await self._get_vix()

        # Extreme VIX - reject new long positions
        if vix > self.vix_extreme_threshold and order.action.lower() == "buy":
            return RiskVote(
                agent="MarketRiskAgent",
                decision=RiskDecision.REJECT,
                risk_score=0.9,
                reasoning=f"VIX at {vix:.1f} - extreme volatility, no new longs",
            )

        # High VIX - reduce size
        if vix > self.vix_high_threshold:
            return RiskVote(
                agent="MarketRiskAgent",
                decision=RiskDecision.ADJUST,
                risk_score=0.7,
                reasoning=f"VIX elevated at {vix:.1f}",
                adjustments=[
                    {
                        "type": "reduce_size",
                        "factor": 0.5,
                        "reason": "high_volatility",
                    }
                ],
            )

        # Check liquidity
        liquidity = await self._check_liquidity(order.symbol)
        if liquidity < self.LIQUIDITY_LOW_THRESHOLD:
            return RiskVote(
                agent="MarketRiskAgent",
                decision=RiskDecision.ADJUST,
                risk_score=0.6,
                reasoning=f"Low liquidity for {order.symbol} ({liquidity:.2f})",
                adjustments=[
                    {
                        "type": "split_order",
                        "max_per_order": 0.01,  # 1% of ADV
                        "reason": "low_liquidity",
                    }
                ],
            )

        # Calculate risk score based on VIX
        risk_score = vix / 100  # Normalize VIX to 0-1 scale

        return RiskVote(
            agent="MarketRiskAgent",
            decision=RiskDecision.APPROVE,
            risk_score=min(risk_score, 1.0),
            reasoning="Market conditions acceptable",
        )

    async def _get_vix(self) -> float:
        """Get current VIX level.

        Returns:
            Current VIX value
        """
        try:
            data = await self.market_data.get_vix()
            return data
        except Exception as e:
            logger.warning(f"Failed to get VIX, using default: {e}")
            return 20.0  # Default moderate VIX

    async def _check_liquidity(self, symbol: str) -> float:
        """Check symbol liquidity.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Liquidity score (0.0 - 1.0)
        """
        try:
            avg_volume = await self.market_data.get_average_volume(symbol)
            # Normalize based on typical volume thresholds
            return min(avg_volume / self.MIN_DAILY_VOLUME, 1.0)
        except Exception as e:
            logger.warning(f"Failed to check liquidity for {symbol}: {e}")
            return 0.5  # Default moderate liquidity
