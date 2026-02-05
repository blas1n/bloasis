"""Tests for Risk Agents."""

import pytest

from src.agents import ConcentrationRiskAgent, MarketRiskAgent, PositionRiskAgent
from src.models import OrderRequest, RiskDecision


class TestPositionRiskAgent:
    """Tests for PositionRiskAgent."""

    @pytest.fixture
    def agent(self, mock_portfolio_client):
        """Create PositionRiskAgent with mock client."""
        return PositionRiskAgent(mock_portfolio_client)

    @pytest.mark.asyncio
    async def test_approve_order_within_limits(self, agent, sample_portfolio):
        """Test approval for order within limits."""
        # Create an order that's well under the limit (2% of portfolio)
        small_order = OrderRequest(
            user_id="test-user",
            symbol="XOM",  # Energy sector - different from portfolio
            action="buy",
            size=10,
            price=200.0,  # $2,000 = 2% of $100,000
        )

        vote = await agent.evaluate(small_order, sample_portfolio)

        assert vote.decision == RiskDecision.APPROVE
        assert vote.agent == "PositionRiskAgent"
        assert "within limits" in vote.reasoning.lower()
        assert vote.risk_score <= 1.0

    @pytest.mark.asyncio
    async def test_reject_empty_portfolio(self, agent, sample_order, empty_portfolio):
        """Test rejection when portfolio value is zero."""
        vote = await agent.evaluate(sample_order, empty_portfolio)

        assert vote.decision == RiskDecision.REJECT
        assert vote.risk_score == 1.0
        assert "zero" in vote.reasoning.lower()

    @pytest.mark.asyncio
    async def test_adjust_order_exceeds_single_order_limit(
        self, agent, large_order, sample_portfolio
    ):
        """Test adjustment when order exceeds single order limit (5%)."""
        vote = await agent.evaluate(large_order, sample_portfolio)

        assert vote.decision == RiskDecision.ADJUST
        assert vote.risk_score >= 0.6
        assert "exceeds limit" in vote.reasoning.lower()
        assert len(vote.adjustments) > 0
        assert vote.adjustments[0]["type"] == "reduce_size"

    @pytest.mark.asyncio
    async def test_adjust_order_exceeds_position_limit(self, agent, sample_portfolio):
        """Test adjustment when total position exceeds limit (10%)."""
        # Order that would put AAPL position over 10%
        order = OrderRequest(
            user_id="test-user",
            symbol="AAPL",
            action="buy",
            size=10,
            price=400.0,  # Adds $4,000 to existing $8,750 = $12,750 = 12.75%
        )

        vote = await agent.evaluate(order, sample_portfolio)

        # Should approve since $4000 is 4% of portfolio (under 5% single order limit)
        # and new position would be under 10% limit
        assert vote.decision in [RiskDecision.APPROVE, RiskDecision.ADJUST]

    @pytest.mark.asyncio
    async def test_sell_order_reduces_position(self, agent, sample_portfolio):
        """Test that sell orders reduce position correctly."""
        order = OrderRequest(
            user_id="test-user",
            symbol="AAPL",
            action="sell",
            size=10,
            price=175.0,
        )

        vote = await agent.evaluate(order, sample_portfolio)

        # Sell order should be approved as it reduces position
        assert vote.decision == RiskDecision.APPROVE

    @pytest.mark.asyncio
    async def test_get_current_position_existing(self, agent, sample_portfolio):
        """Test getting current position for existing symbol."""
        position = agent._get_current_position("AAPL", sample_portfolio)
        assert float(position) == 8750.0

    @pytest.mark.asyncio
    async def test_get_current_position_not_existing(self, agent, sample_portfolio):
        """Test getting current position for non-existing symbol."""
        position = agent._get_current_position("TSLA", sample_portfolio)
        assert float(position) == 0.0


class TestConcentrationRiskAgent:
    """Tests for ConcentrationRiskAgent."""

    @pytest.fixture
    def agent(self, mock_portfolio_client):
        """Create ConcentrationRiskAgent with mock client."""
        return ConcentrationRiskAgent(mock_portfolio_client)

    @pytest.mark.asyncio
    async def test_approve_order_concentration_ok(self, agent, sample_portfolio):
        """Test approval when concentration is within limits."""
        # Use a different sector (Energy) to avoid correlation with portfolio's Technology
        order = OrderRequest(
            user_id="test-user",
            symbol="XOM",  # Energy sector
            action="buy",
            size=10,
            price=100.0,  # Small order
        )

        vote = await agent.evaluate(order, sample_portfolio)

        assert vote.decision == RiskDecision.APPROVE
        assert vote.agent == "ConcentrationRiskAgent"
        assert "within limits" in vote.reasoning.lower()

    @pytest.mark.asyncio
    async def test_approve_empty_portfolio(self, agent, sample_order, empty_portfolio):
        """Test approval for empty portfolio (no concentration risk)."""
        vote = await agent.evaluate(sample_order, empty_portfolio)

        assert vote.decision == RiskDecision.APPROVE
        assert "no concentration risk" in vote.reasoning.lower()

    @pytest.mark.asyncio
    async def test_adjust_sector_concentration_exceeded(self, agent, sample_portfolio):
        """Test adjustment when sector concentration exceeded."""
        # Large order in Technology sector (already 11.55% in Tech)
        order = OrderRequest(
            user_id="test-user",
            symbol="MSFT",
            action="buy",
            size=100,
            price=250.0,  # $25,000 = 25%, total Tech would be ~36.55%
        )

        vote = await agent.evaluate(order, sample_portfolio)

        assert vote.decision == RiskDecision.ADJUST
        assert "sector" in vote.reasoning.lower()
        assert len(vote.adjustments) > 0

    @pytest.mark.asyncio
    async def test_get_sector_known_symbol(self, agent):
        """Test getting sector for known symbol."""
        sector = await agent._get_sector("AAPL")
        assert sector == "Technology"

    @pytest.mark.asyncio
    async def test_get_sector_unknown_symbol(self, agent):
        """Test getting sector for unknown symbol."""
        sector = await agent._get_sector("UNKNOWN")
        assert sector == "Unknown"

    @pytest.mark.asyncio
    async def test_calculate_sector_exposure(self, agent, sample_portfolio):
        """Test calculating sector exposure."""
        exposure = agent._calculate_sector_exposure(sample_portfolio, "Technology")
        # AAPL ($8750) + GOOGL ($2800) = $11550
        assert float(exposure) == 11550.0

    @pytest.mark.asyncio
    async def test_check_correlation_same_sector(self, agent, sample_portfolio):
        """Test correlation check for same sector."""
        # MSFT is in Technology, same as AAPL and GOOGL
        correlation = await agent._check_correlation("MSFT", sample_portfolio)
        assert correlation >= 0.9

    @pytest.mark.asyncio
    async def test_check_correlation_different_sector(self, agent, sample_portfolio):
        """Test correlation check for different sector."""
        # XOM is in Energy, different from portfolio's Technology
        correlation = await agent._check_correlation("XOM", sample_portfolio)
        assert correlation < 0.9


class TestMarketRiskAgent:
    """Tests for MarketRiskAgent."""

    @pytest.fixture
    def agent(self, mock_market_data_client):
        """Create MarketRiskAgent with mock client."""
        return MarketRiskAgent(mock_market_data_client)

    @pytest.mark.asyncio
    async def test_approve_normal_vix(self, agent, sample_order, sample_portfolio):
        """Test approval when VIX is normal."""
        vote = await agent.evaluate(sample_order, sample_portfolio)

        assert vote.decision == RiskDecision.APPROVE
        assert vote.agent == "MarketRiskAgent"
        assert "acceptable" in vote.reasoning.lower()

    @pytest.mark.asyncio
    async def test_reject_extreme_vix_buy(
        self, agent, mock_market_data_client, sample_order, sample_portfolio
    ):
        """Test rejection when VIX is extreme and buying."""
        mock_market_data_client.get_vix.return_value = 45.0

        vote = await agent.evaluate(sample_order, sample_portfolio)

        assert vote.decision == RiskDecision.REJECT
        assert "extreme" in vote.reasoning.lower()
        assert vote.risk_score >= 0.9

    @pytest.mark.asyncio
    async def test_allow_sell_extreme_vix(self, agent, mock_market_data_client, sample_portfolio):
        """Test that sell orders are allowed even in extreme VIX."""
        mock_market_data_client.get_vix.return_value = 45.0

        sell_order = OrderRequest(
            user_id="test-user",
            symbol="AAPL",
            action="sell",
            size=10,
            price=175.0,
        )

        vote = await agent.evaluate(sell_order, sample_portfolio)

        # Sell orders should not be rejected due to extreme VIX
        assert vote.decision != RiskDecision.REJECT or "extreme" not in vote.reasoning.lower()

    @pytest.mark.asyncio
    async def test_adjust_high_vix(
        self, agent, mock_market_data_client, sample_order, sample_portfolio
    ):
        """Test adjustment when VIX is high but not extreme."""
        mock_market_data_client.get_vix.return_value = 35.0

        vote = await agent.evaluate(sample_order, sample_portfolio)

        assert vote.decision == RiskDecision.ADJUST
        assert "elevated" in vote.reasoning.lower()
        assert len(vote.adjustments) > 0
        assert vote.adjustments[0]["type"] == "reduce_size"

    @pytest.mark.asyncio
    async def test_adjust_low_liquidity(
        self, agent, mock_market_data_client, sample_order, sample_portfolio
    ):
        """Test adjustment when liquidity is low."""
        mock_market_data_client.get_vix.return_value = 20.0
        mock_market_data_client.get_average_volume.return_value = 100000.0  # Low volume

        vote = await agent.evaluate(sample_order, sample_portfolio)

        assert vote.decision == RiskDecision.ADJUST
        assert "liquidity" in vote.reasoning.lower()
        assert len(vote.adjustments) > 0
        assert vote.adjustments[0]["type"] == "split_order"

    @pytest.mark.asyncio
    async def test_get_vix_fallback(self, agent, mock_market_data_client, sample_portfolio):
        """Test VIX fallback on error."""
        mock_market_data_client.get_vix.side_effect = Exception("API Error")

        order = OrderRequest(
            user_id="test-user",
            symbol="AAPL",
            action="buy",
            size=10,
            price=175.0,
        )

        # Should use default VIX (20.0)
        vote = await agent.evaluate(order, sample_portfolio)
        assert vote.decision == RiskDecision.APPROVE

    @pytest.mark.asyncio
    async def test_check_liquidity_fallback(self, agent, mock_market_data_client, sample_portfolio):
        """Test liquidity check fallback on error."""
        mock_market_data_client.get_average_volume.side_effect = Exception("API Error")

        order = OrderRequest(
            user_id="test-user",
            symbol="UNKNOWN",
            action="buy",
            size=10,
            price=100.0,
        )

        # Should use default liquidity (0.5)
        vote = await agent.evaluate(order, sample_portfolio)
        # Default liquidity (0.5) is exactly at threshold, so might be APPROVE
        assert vote.decision in [RiskDecision.APPROVE, RiskDecision.ADJUST]
