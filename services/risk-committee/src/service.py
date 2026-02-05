"""Risk Committee Service - Multi-agent risk assessment."""

import logging
from typing import TYPE_CHECKING

import grpc
from shared.generated import risk_committee_pb2, risk_committee_pb2_grpc

from .config import config
from .models import CommitteeDecision, OrderRequest, Portfolio, RiskDecision, RiskVote

if TYPE_CHECKING:
    from .clients.market_data_client import MarketDataClient
    from .clients.portfolio_client import PortfolioClient
    from .utils.event_publisher import EventPublisher

logger = logging.getLogger(__name__)


class RiskCommitteeServicer(risk_committee_pb2_grpc.RiskCommitteeServiceServicer):
    """Risk Committee Service - evaluates orders before execution."""

    def __init__(
        self,
        portfolio_client: "PortfolioClient",
        market_data_client: "MarketDataClient",
        event_publisher: "EventPublisher",
        agents: list | None = None,
    ) -> None:
        """Initialize Risk Committee servicer.

        Args:
            portfolio_client: Client for Portfolio Service
            market_data_client: Client for Market Data Service
            event_publisher: Publisher for risk decision events
            agents: Optional list of risk agents (for testing)
        """
        self.portfolio = portfolio_client
        self.market_data = market_data_client
        self.publisher = event_publisher

        # Initialize risk agents if not provided
        if agents is not None:
            self.agents = agents
        else:
            from .agents import (
                ConcentrationRiskAgent,
                MarketRiskAgent,
                PositionRiskAgent,
            )

            self.agents = [
                PositionRiskAgent(portfolio_client),
                ConcentrationRiskAgent(portfolio_client),
                MarketRiskAgent(market_data_client),
            ]

    async def EvaluateOrder(
        self,
        request: risk_committee_pb2.EvaluateOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> risk_committee_pb2.EvaluateOrderResponse:
        """Evaluate a single order for risk.

        All agents vote, then consensus determines outcome.

        Args:
            request: Order evaluation request
            context: gRPC context

        Returns:
            Risk evaluation response with decision and votes
        """
        logger.info(f"Evaluating order: {request.symbol} {request.action}")

        # Validate request
        if not request.user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")
        if not request.symbol:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "symbol is required")
        if request.size <= 0:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "size must be positive")
        if request.price <= 0:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "price must be positive")

        # Get portfolio context
        try:
            portfolio = await self.portfolio.get_positions(request.user_id)
        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to get portfolio: {e}")

        # Create order request model
        order = OrderRequest(
            user_id=request.user_id,
            symbol=request.symbol,
            action=request.action,
            size=request.size,
            price=request.price,
            order_type=request.order_type or "market",
        )

        # Collect votes from all agents
        votes = []
        for agent in self.agents:
            vote = await agent.evaluate(order, portfolio)
            votes.append(vote)

        # Determine consensus
        decision = self._determine_consensus(votes)

        # Publish decision event
        await self._publish_decision(order, decision)

        logger.info(
            f"Order {request.symbol} {request.action}: {decision.decision.value} "
            f"(score={decision.risk_score:.2f})"
        )

        return self._to_response(decision)

    async def EvaluateBatch(
        self,
        request: risk_committee_pb2.EvaluateBatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> risk_committee_pb2.EvaluateBatchResponse:
        """Evaluate multiple orders together for correlation risk.

        Args:
            request: Batch evaluation request
            context: gRPC context

        Returns:
            Batch evaluation response with individual decisions
        """
        logger.info(f"Evaluating batch of {len(request.orders)} orders")

        # Validate request
        if not request.user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")
        if not request.orders:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "orders list is empty")

        # Get portfolio once for all orders
        try:
            portfolio = await self.portfolio.get_positions(request.user_id)
        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to get portfolio: {e}")

        # Evaluate each order
        decisions: list[tuple[risk_committee_pb2.OrderToEvaluate, CommitteeDecision]] = []
        for order_proto in request.orders:
            order = OrderRequest(
                user_id=request.user_id,
                symbol=order_proto.symbol,
                action=order_proto.action,
                size=order_proto.size,
                price=order_proto.price,
            )

            votes = []
            for agent in self.agents:
                vote = await agent.evaluate(order, portfolio)
                votes.append(vote)

            decision = self._determine_consensus(votes)
            decisions.append((order_proto, decision))

        # Check cross-order correlation risk
        correlation_warnings = self._check_correlation_risk(decisions)

        return self._to_batch_response(decisions, correlation_warnings)

    async def GetRiskLimits(
        self,
        request: risk_committee_pb2.GetRiskLimitsRequest,
        context: grpc.aio.ServicerContext,
    ) -> risk_committee_pb2.GetRiskLimitsResponse:
        """Get risk limits for a user.

        Args:
            request: Risk limits request
            context: gRPC context

        Returns:
            User's risk limits
        """
        logger.info(f"Getting risk limits for user: {request.user_id}")

        if not request.user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        # Get current portfolio risk score
        try:
            portfolio = await self.portfolio.get_positions(request.user_id)
            current_risk = self._calculate_portfolio_risk(portfolio)
        except Exception:
            current_risk = 0.0

        return risk_committee_pb2.GetRiskLimitsResponse(
            user_id=request.user_id,
            max_position_size=config.default_max_position_size,
            max_sector_concentration=config.default_max_sector_concentration,
            max_single_order=config.default_max_single_order,
            current_risk_score=current_risk,
        )

    def _determine_consensus(self, votes: list[RiskVote]) -> CommitteeDecision:
        """Determine committee consensus from votes.

        Rules:
        - All approve -> Approved
        - Any reject with score > 0.8 -> Rejected (veto)
        - Any adjust -> Adjust (with suggested changes)

        Args:
            votes: List of agent votes

        Returns:
            Committee decision
        """
        if not votes:
            return CommitteeDecision(
                approved=False,
                decision=RiskDecision.REJECT,
                risk_score=1.0,
                votes=[],
                adjustments=[],
                warnings=["No risk agents available"],
                reasoning="Cannot evaluate without risk agents",
            )

        avg_score = sum(v.risk_score for v in votes) / len(votes)
        all_adjustments: list[dict] = []
        all_warnings: list[str] = []

        # Check for vetoes (high risk rejections)
        for vote in votes:
            if vote.decision == RiskDecision.REJECT and vote.risk_score > 0.8:
                return CommitteeDecision(
                    approved=False,
                    decision=RiskDecision.REJECT,
                    risk_score=vote.risk_score,
                    votes=votes,
                    adjustments=[],
                    warnings=[vote.reasoning],
                    reasoning=f"Vetoed by {vote.agent}: {vote.reasoning}",
                )

            if vote.adjustments:
                all_adjustments.extend(vote.adjustments)
            if vote.decision == RiskDecision.ADJUST:
                all_warnings.append(f"{vote.agent}: {vote.reasoning}")

        # Check for adjustments needed
        if all_adjustments:
            return CommitteeDecision(
                approved=True,
                decision=RiskDecision.ADJUST,
                risk_score=avg_score,
                votes=votes,
                adjustments=all_adjustments,
                warnings=all_warnings,
                reasoning="Approved with adjustments",
            )

        # All clear
        return CommitteeDecision(
            approved=True,
            decision=RiskDecision.APPROVE,
            risk_score=avg_score,
            votes=votes,
            adjustments=[],
            warnings=[],
            reasoning="Approved by consensus",
        )

    def _check_correlation_risk(
        self,
        decisions: list[tuple[risk_committee_pb2.OrderToEvaluate, CommitteeDecision]],
    ) -> list[str]:
        """Check for cross-order correlation risk.

        Args:
            decisions: List of (order, decision) tuples

        Returns:
            List of correlation warnings
        """
        warnings = []

        # Check for multiple orders in same sector
        sectors: dict[str, list[str]] = {}
        for order, _ in decisions:
            # In production, would lookup sector from market data
            sector = "Technology"  # Placeholder
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append(order.symbol)

        for sector, symbols in sectors.items():
            if len(symbols) > 2:
                warnings.append(
                    f"Multiple orders ({len(symbols)}) in {sector} sector: {', '.join(symbols)}"
                )

        # Check for large total exposure
        total_value = sum(
            order.size * order.price for order, decision in decisions if decision.approved
        )
        if total_value > 100000:  # Example threshold
            warnings.append(f"Large total batch exposure: ${total_value:,.2f}")

        return warnings

    def _calculate_portfolio_risk(self, portfolio: Portfolio) -> float:
        """Calculate overall portfolio risk score.

        Args:
            portfolio: User's portfolio

        Returns:
            Risk score 0.0 - 1.0
        """
        if not portfolio.positions or portfolio.total_value == 0:
            return 0.0

        # Calculate concentration risk
        max_position_pct = 0.0
        for position in portfolio.positions:
            pct = position.market_value / portfolio.total_value
            max_position_pct = max(max_position_pct, pct)

        # Higher concentration = higher risk
        return min(max_position_pct / config.default_max_position_size, 1.0)

    async def _publish_decision(
        self,
        order: OrderRequest,
        decision: CommitteeDecision,
    ) -> None:
        """Publish risk decision event.

        Args:
            order: The order that was evaluated
            decision: The committee decision
        """
        try:
            await self.publisher.publish_risk_decision(
                user_id=order.user_id,
                symbol=order.symbol,
                action=order.action,
                approved=decision.approved,
                risk_score=decision.risk_score,
                reasoning=decision.reasoning,
            )
        except Exception as e:
            logger.warning(f"Failed to publish risk decision event: {e}")

    def _to_response(self, decision: CommitteeDecision) -> risk_committee_pb2.EvaluateOrderResponse:
        """Convert CommitteeDecision to proto response.

        Args:
            decision: Committee decision

        Returns:
            Proto response
        """
        # Convert votes
        proto_votes = [
            risk_committee_pb2.RiskVote(
                agent=v.agent,
                decision=v.decision.value,
                risk_score=v.risk_score,
                reasoning=v.reasoning,
            )
            for v in decision.votes
        ]

        # Convert adjustments
        proto_adjustments = [
            risk_committee_pb2.Adjustment(
                type=adj.get("type", ""),
                value=adj.get("value", 0.0),
                reason=adj.get("reason", ""),
                sector=adj.get("sector", ""),
                target_pct=adj.get("target_pct", 0.0),
            )
            for adj in decision.adjustments
        ]

        return risk_committee_pb2.EvaluateOrderResponse(
            approved=decision.approved,
            decision=decision.decision.value,
            risk_score=decision.risk_score,
            votes=proto_votes,
            adjustments=proto_adjustments,
            warnings=decision.warnings,
            reasoning=decision.reasoning,
        )

    def _to_batch_response(
        self,
        decisions: list[tuple[risk_committee_pb2.OrderToEvaluate, CommitteeDecision]],
        correlation_warnings: list[str],
    ) -> risk_committee_pb2.EvaluateBatchResponse:
        """Convert batch decisions to proto response.

        Args:
            decisions: List of (order, decision) tuples
            correlation_warnings: Cross-order warnings

        Returns:
            Proto batch response
        """
        # Calculate overall risk score
        if decisions:
            overall_score = sum(d.risk_score for _, d in decisions) / len(decisions)
        else:
            overall_score = 0.0

        # Convert individual decisions
        order_decisions = []
        for order, decision in decisions:
            proto_adjustments = [
                risk_committee_pb2.Adjustment(
                    type=adj.get("type", ""),
                    value=adj.get("value", 0.0),
                    reason=adj.get("reason", ""),
                    sector=adj.get("sector", ""),
                    target_pct=adj.get("target_pct", 0.0),
                )
                for adj in decision.adjustments
            ]

            order_decisions.append(
                risk_committee_pb2.OrderDecision(
                    symbol=order.symbol,
                    approved=decision.approved,
                    decision=decision.decision.value,
                    risk_score=decision.risk_score,
                    adjustments=proto_adjustments,
                )
            )

        return risk_committee_pb2.EvaluateBatchResponse(
            decisions=order_decisions,
            overall_risk_score=overall_score,
            cross_order_warnings=correlation_warnings,
        )
