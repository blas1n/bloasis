"""Tests for Risk Committee Service."""

from unittest.mock import AsyncMock

import pytest
from shared.generated import risk_committee_pb2

from src.models import CommitteeDecision, RiskDecision, RiskVote
from src.service import RiskCommitteeServicer


class TestRiskCommitteeServicer:
    """Tests for RiskCommitteeServicer."""

    @pytest.fixture
    def mock_agents(self):
        """Create mock risk agents."""
        agent1 = AsyncMock()
        agent1.evaluate = AsyncMock(
            return_value=RiskVote(
                agent="MockAgent1",
                decision=RiskDecision.APPROVE,
                risk_score=0.3,
                reasoning="All good",
            )
        )

        agent2 = AsyncMock()
        agent2.evaluate = AsyncMock(
            return_value=RiskVote(
                agent="MockAgent2",
                decision=RiskDecision.APPROVE,
                risk_score=0.2,
                reasoning="Looking fine",
            )
        )

        return [agent1, agent2]

    @pytest.fixture
    def servicer(
        self, mock_portfolio_client, mock_market_data_client, mock_event_publisher, mock_agents
    ):
        """Create RiskCommitteeServicer with mocks."""
        return RiskCommitteeServicer(
            portfolio_client=mock_portfolio_client,
            market_data_client=mock_market_data_client,
            event_publisher=mock_event_publisher,
            agents=mock_agents,
        )

    @pytest.mark.asyncio
    async def test_evaluate_order_approved(self, servicer, mock_grpc_context, mock_event_publisher):
        """Test successful order evaluation with approval."""
        request = risk_committee_pb2.EvaluateOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            action="buy",
            size=10,
            price=175.0,
            order_type="market",
        )

        response = await servicer.EvaluateOrder(request, mock_grpc_context)

        assert response.approved is True
        assert response.decision == "approve"
        assert len(response.votes) == 2
        mock_event_publisher.publish_risk_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_order_missing_user_id(self, servicer, mock_grpc_context):
        """Test order evaluation with missing user_id."""
        request = risk_committee_pb2.EvaluateOrderRequest(
            symbol="AAPL",
            action="buy",
            size=10,
            price=175.0,
        )

        await servicer.EvaluateOrder(request, mock_grpc_context)
        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_evaluate_order_missing_symbol(self, servicer, mock_grpc_context):
        """Test order evaluation with missing symbol."""
        request = risk_committee_pb2.EvaluateOrderRequest(
            user_id="test-user",
            action="buy",
            size=10,
            price=175.0,
        )

        await servicer.EvaluateOrder(request, mock_grpc_context)
        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_evaluate_order_invalid_size(self, servicer, mock_grpc_context):
        """Test order evaluation with invalid size."""
        request = risk_committee_pb2.EvaluateOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            action="buy",
            size=-10,
            price=175.0,
        )

        await servicer.EvaluateOrder(request, mock_grpc_context)
        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_evaluate_order_invalid_price(self, servicer, mock_grpc_context):
        """Test order evaluation with invalid price."""
        request = risk_committee_pb2.EvaluateOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            action="buy",
            size=10,
            price=0,
        )

        await servicer.EvaluateOrder(request, mock_grpc_context)
        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_evaluate_batch(
        self,
        mock_portfolio_client,
        mock_market_data_client,
        mock_event_publisher,
        mock_agents,
        mock_grpc_context,
    ):
        """Test batch order evaluation."""
        servicer = RiskCommitteeServicer(
            portfolio_client=mock_portfolio_client,
            market_data_client=mock_market_data_client,
            event_publisher=mock_event_publisher,
            agents=mock_agents,
        )

        request = risk_committee_pb2.EvaluateBatchRequest(
            user_id="test-user",
            orders=[
                risk_committee_pb2.OrderToEvaluate(
                    symbol="AAPL", action="buy", size=10, price=175.0
                ),
                risk_committee_pb2.OrderToEvaluate(
                    symbol="GOOGL", action="buy", size=5, price=140.0
                ),
            ],
        )

        response = await servicer.EvaluateBatch(request, mock_grpc_context)

        assert len(response.decisions) == 2
        assert response.overall_risk_score > 0

    @pytest.mark.asyncio
    async def test_evaluate_batch_empty_orders(self, servicer, mock_grpc_context):
        """Test batch evaluation with empty orders."""
        request = risk_committee_pb2.EvaluateBatchRequest(
            user_id="test-user",
            orders=[],
        )

        await servicer.EvaluateBatch(request, mock_grpc_context)
        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_evaluate_batch_missing_user_id(self, servicer, mock_grpc_context):
        """Test batch evaluation with missing user_id."""
        request = risk_committee_pb2.EvaluateBatchRequest(
            orders=[
                risk_committee_pb2.OrderToEvaluate(
                    symbol="AAPL", action="buy", size=10, price=175.0
                ),
            ],
        )

        await servicer.EvaluateBatch(request, mock_grpc_context)
        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_get_risk_limits(self, servicer, mock_grpc_context):
        """Test getting risk limits."""
        request = risk_committee_pb2.GetRiskLimitsRequest(user_id="test-user")

        response = await servicer.GetRiskLimits(request, mock_grpc_context)

        assert response.user_id == "test-user"
        assert response.max_position_size == 0.10
        assert response.max_sector_concentration == 0.30
        assert response.max_single_order == 0.05

    @pytest.mark.asyncio
    async def test_get_risk_limits_missing_user_id(self, servicer, mock_grpc_context):
        """Test getting risk limits with missing user_id."""
        request = risk_committee_pb2.GetRiskLimitsRequest()

        await servicer.GetRiskLimits(request, mock_grpc_context)
        mock_grpc_context.abort.assert_called()


class TestConsensusLogic:
    """Tests for consensus determination logic."""

    @pytest.fixture
    def servicer(self, mock_portfolio_client, mock_market_data_client, mock_event_publisher):
        """Create servicer for testing consensus logic."""
        return RiskCommitteeServicer(
            portfolio_client=mock_portfolio_client,
            market_data_client=mock_market_data_client,
            event_publisher=mock_event_publisher,
            agents=[],
        )

    def test_consensus_all_approve(self, servicer):
        """Test consensus when all agents approve."""
        votes = [
            RiskVote(agent="Agent1", decision=RiskDecision.APPROVE, risk_score=0.2, reasoning="OK"),
            RiskVote(agent="Agent2", decision=RiskDecision.APPROVE, risk_score=0.3, reasoning="OK"),
        ]

        decision = servicer._determine_consensus(votes)

        assert decision.approved is True
        assert decision.decision == RiskDecision.APPROVE
        assert decision.risk_score == 0.25  # Average

    def test_consensus_veto_high_risk(self, servicer):
        """Test veto when one agent rejects with high risk score."""
        votes = [
            RiskVote(
                agent="Agent1",
                decision=RiskDecision.REJECT,
                risk_score=0.9,
                reasoning="Too risky",
            ),
            RiskVote(agent="Agent2", decision=RiskDecision.APPROVE, risk_score=0.2, reasoning="OK"),
        ]

        decision = servicer._determine_consensus(votes)

        assert decision.approved is False
        assert decision.decision == RiskDecision.REJECT
        assert "Vetoed" in decision.reasoning

    def test_consensus_no_veto_low_risk_reject(self, servicer):
        """Test no veto when rejection has low risk score."""
        votes = [
            RiskVote(
                agent="Agent1",
                decision=RiskDecision.REJECT,
                risk_score=0.5,  # Below 0.8 threshold
                reasoning="Minor concern",
            ),
            RiskVote(agent="Agent2", decision=RiskDecision.APPROVE, risk_score=0.2, reasoning="OK"),
        ]

        decision = servicer._determine_consensus(votes)

        # Should not veto since risk score < 0.8
        assert decision.approved is True or decision.decision == RiskDecision.ADJUST

    def test_consensus_adjust_with_adjustments(self, servicer):
        """Test adjust decision when adjustments are suggested."""
        votes = [
            RiskVote(
                agent="Agent1",
                decision=RiskDecision.ADJUST,
                risk_score=0.6,
                reasoning="Reduce size",
                adjustments=[{"type": "reduce_size", "value": 0.5}],
            ),
            RiskVote(agent="Agent2", decision=RiskDecision.APPROVE, risk_score=0.2, reasoning="OK"),
        ]

        decision = servicer._determine_consensus(votes)

        assert decision.approved is True
        assert decision.decision == RiskDecision.ADJUST
        assert len(decision.adjustments) > 0

    def test_consensus_empty_votes(self, servicer):
        """Test consensus with no votes."""
        decision = servicer._determine_consensus([])

        assert decision.approved is False
        assert decision.decision == RiskDecision.REJECT
        assert "without risk agents" in decision.reasoning.lower()


class TestCorrelationRisk:
    """Tests for cross-order correlation risk."""

    @pytest.fixture
    def servicer(self, mock_portfolio_client, mock_market_data_client, mock_event_publisher):
        """Create servicer for testing."""
        return RiskCommitteeServicer(
            portfolio_client=mock_portfolio_client,
            market_data_client=mock_market_data_client,
            event_publisher=mock_event_publisher,
            agents=[],
        )

    def test_correlation_multiple_same_sector(self, servicer):
        """Test correlation warning for multiple orders in same sector."""
        decisions = [
            (
                risk_committee_pb2.OrderToEvaluate(symbol="AAPL", action="buy", size=10, price=175),
                CommitteeDecision(
                    approved=True,
                    decision=RiskDecision.APPROVE,
                    risk_score=0.3,
                    votes=[],
                    adjustments=[],
                    warnings=[],
                    reasoning="OK",
                ),
            ),
            (
                risk_committee_pb2.OrderToEvaluate(symbol="MSFT", action="buy", size=10, price=350),
                CommitteeDecision(
                    approved=True,
                    decision=RiskDecision.APPROVE,
                    risk_score=0.3,
                    votes=[],
                    adjustments=[],
                    warnings=[],
                    reasoning="OK",
                ),
            ),
            (
                risk_committee_pb2.OrderToEvaluate(symbol="NVDA", action="buy", size=10, price=500),
                CommitteeDecision(
                    approved=True,
                    decision=RiskDecision.APPROVE,
                    risk_score=0.3,
                    votes=[],
                    adjustments=[],
                    warnings=[],
                    reasoning="OK",
                ),
            ),
        ]

        warnings = servicer._check_correlation_risk(decisions)

        assert len(warnings) > 0
        assert any("Multiple orders" in w for w in warnings)

    def test_correlation_large_batch_exposure(self, servicer):
        """Test warning for large total batch exposure."""
        decisions = [
            (
                risk_committee_pb2.OrderToEvaluate(
                    symbol="AAPL", action="buy", size=500, price=175
                ),  # $87,500
                CommitteeDecision(
                    approved=True,
                    decision=RiskDecision.APPROVE,
                    risk_score=0.3,
                    votes=[],
                    adjustments=[],
                    warnings=[],
                    reasoning="OK",
                ),
            ),
            (
                risk_committee_pb2.OrderToEvaluate(
                    symbol="GOOGL", action="buy", size=200, price=140
                ),  # $28,000
                CommitteeDecision(
                    approved=True,
                    decision=RiskDecision.APPROVE,
                    risk_score=0.3,
                    votes=[],
                    adjustments=[],
                    warnings=[],
                    reasoning="OK",
                ),
            ),
        ]

        warnings = servicer._check_correlation_risk(decisions)

        assert any("Large total" in w for w in warnings)


class TestProtoConversion:
    """Tests for proto conversion methods."""

    @pytest.fixture
    def servicer(self, mock_portfolio_client, mock_market_data_client, mock_event_publisher):
        """Create servicer for testing."""
        return RiskCommitteeServicer(
            portfolio_client=mock_portfolio_client,
            market_data_client=mock_market_data_client,
            event_publisher=mock_event_publisher,
            agents=[],
        )

    def test_to_response_basic(self, servicer):
        """Test basic proto response conversion."""
        decision = CommitteeDecision(
            approved=True,
            decision=RiskDecision.APPROVE,
            risk_score=0.3,
            votes=[
                RiskVote(
                    agent="TestAgent",
                    decision=RiskDecision.APPROVE,
                    risk_score=0.3,
                    reasoning="OK",
                )
            ],
            adjustments=[],
            warnings=[],
            reasoning="Approved",
        )

        response = servicer._to_response(decision)

        assert response.approved is True
        assert response.decision == "approve"
        assert response.risk_score == 0.3
        assert len(response.votes) == 1
        assert response.votes[0].agent == "TestAgent"

    def test_to_response_with_adjustments(self, servicer):
        """Test proto response with adjustments."""
        decision = CommitteeDecision(
            approved=True,
            decision=RiskDecision.ADJUST,
            risk_score=0.6,
            votes=[],
            adjustments=[
                {"type": "reduce_size", "value": 0.5, "reason": "high_risk"},
                {"type": "split_order", "value": 0.01, "reason": "low_liquidity"},
            ],
            warnings=["Warning 1", "Warning 2"],
            reasoning="Approved with adjustments",
        )

        response = servicer._to_response(decision)

        assert response.decision == "adjust"
        assert len(response.adjustments) == 2
        assert len(response.warnings) == 2

    def test_to_batch_response(self, servicer):
        """Test batch proto response conversion."""
        decisions = [
            (
                risk_committee_pb2.OrderToEvaluate(symbol="AAPL", action="buy", size=10, price=175),
                CommitteeDecision(
                    approved=True,
                    decision=RiskDecision.APPROVE,
                    risk_score=0.3,
                    votes=[],
                    adjustments=[],
                    warnings=[],
                    reasoning="OK",
                ),
            ),
            (
                risk_committee_pb2.OrderToEvaluate(symbol="GOOGL", action="buy", size=5, price=140),
                CommitteeDecision(
                    approved=True,
                    decision=RiskDecision.APPROVE,
                    risk_score=0.4,
                    votes=[],
                    adjustments=[],
                    warnings=[],
                    reasoning="OK",
                ),
            ),
        ]

        response = servicer._to_batch_response(decisions, ["Warning 1"])

        assert len(response.decisions) == 2
        assert response.overall_risk_score == 0.35  # Average
        assert len(response.cross_order_warnings) == 1
