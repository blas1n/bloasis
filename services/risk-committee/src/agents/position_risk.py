"""Position Risk Agent - Checks position sizing limits."""

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from ..config import config
from ..models import OrderRequest, Portfolio, RiskDecision, RiskVote

if TYPE_CHECKING:
    from ..clients.portfolio_client import PortfolioClient

logger = logging.getLogger(__name__)


class PositionRiskAgent:
    """Evaluates position size risk.

    Checks:
    - Single order size limit
    - Total position size limit
    - Account equity requirements
    """

    def __init__(self, portfolio_client: "PortfolioClient") -> None:
        """Initialize Position Risk Agent.

        Args:
            portfolio_client: Client for Portfolio Service
        """
        self.portfolio = portfolio_client
        self.max_position_size = Decimal(str(config.default_max_position_size))
        self.max_single_order = Decimal(str(config.default_max_single_order))

    async def evaluate(self, order: OrderRequest, portfolio: Portfolio) -> RiskVote:
        """Evaluate position size risk.

        Args:
            order: Order to evaluate
            portfolio: Current portfolio state

        Returns:
            Risk vote with decision and reasoning
        """
        # Calculate order size as percentage of portfolio
        order_value = Decimal(str(order.size)) * Decimal(str(order.price))
        portfolio_value = Decimal(str(portfolio.total_value))

        # Check for zero portfolio value
        if portfolio_value == 0:
            return RiskVote(
                agent="PositionRiskAgent",
                decision=RiskDecision.REJECT,
                risk_score=1.0,
                reasoning="Portfolio value is zero",
            )

        order_pct = order_value / portfolio_value

        # Check single order limit
        if order_pct > self.max_single_order:
            return RiskVote(
                agent="PositionRiskAgent",
                decision=RiskDecision.ADJUST,
                risk_score=0.7,
                reasoning=(
                    f"Order size {float(order_pct):.1%} exceeds limit "
                    f"{float(self.max_single_order):.1%}"
                ),
                adjustments=[
                    {
                        "type": "reduce_size",
                        "target_pct": float(self.max_single_order),
                        "reason": "single_order_limit",
                    }
                ],
            )

        # Check total position limit
        current_position = self._get_current_position(order.symbol, portfolio)
        new_position_value = current_position + order_value

        # For sell orders, reduce position
        if order.action.lower() == "sell":
            new_position_value = current_position - order_value

        new_position_pct = new_position_value / portfolio_value

        if new_position_pct > self.max_position_size:
            max_additional = self.max_position_size - (current_position / portfolio_value)
            return RiskVote(
                agent="PositionRiskAgent",
                decision=RiskDecision.ADJUST,
                risk_score=0.6,
                reasoning=(
                    f"Total position {float(new_position_pct):.1%} would exceed limit "
                    f"{float(self.max_position_size):.1%}"
                ),
                adjustments=[
                    {
                        "type": "reduce_size",
                        "max_additional": float(max(max_additional, Decimal("0"))),
                        "reason": "position_limit",
                    }
                ],
            )

        # Calculate risk score based on how close to limit
        risk_score = float(order_pct / self.max_single_order)

        return RiskVote(
            agent="PositionRiskAgent",
            decision=RiskDecision.APPROVE,
            risk_score=min(risk_score, 1.0),
            reasoning="Position size within limits",
        )

    def _get_current_position(self, symbol: str, portfolio: Portfolio) -> Decimal:
        """Get current position value for a symbol.

        Args:
            symbol: Stock ticker symbol
            portfolio: Current portfolio

        Returns:
            Current position value as Decimal
        """
        for position in portfolio.positions:
            if position.symbol == symbol:
                return Decimal(str(position.market_value))
        return Decimal("0")
