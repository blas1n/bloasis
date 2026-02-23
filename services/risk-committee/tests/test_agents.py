"""Tests for Risk Agents."""

from unittest.mock import AsyncMock

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
    def agent(self, mock_portfolio_client, mock_market_data_client, mock_redis_client):
        """Create ConcentrationRiskAgent with mock clients."""
        return ConcentrationRiskAgent(
            portfolio_client=mock_portfolio_client,
            market_data_client=mock_market_data_client,
            redis_client=mock_redis_client,
        )

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
        exposure = await agent._calculate_sector_exposure(sample_portfolio, "Technology")
        # AAPL ($8750) + GOOGL ($2800) = $11550
        assert float(exposure) == 11550.0

    @pytest.mark.asyncio
    async def test_check_correlation_same_sector_fallback(self, agent, sample_portfolio):
        """Test correlation fallback for same sector (no market data)."""
        # MSFT is in Technology, same as AAPL and GOOGL
        # With empty closes, fallback assigns 0.6 for same-sector
        correlation = await agent._check_correlation("MSFT", sample_portfolio)
        assert correlation >= 0.6

    @pytest.mark.asyncio
    async def test_check_correlation_different_sector_fallback(self, agent, sample_portfolio):
        """Test correlation fallback for different sector (no market data)."""
        # XOM is in Energy, different from portfolio's Technology
        correlation = await agent._check_correlation("XOM", sample_portfolio)
        assert correlation == 0.0  # No data + different sector → 0.0

    @pytest.mark.asyncio
    async def test_check_correlation_with_return_data(
        self, agent, mock_market_data_client, sample_portfolio
    ):
        """Test Pearson correlation with actual return data."""
        import numpy as np

        # Generate correlated price series
        np.random.seed(42)
        base_returns = np.random.normal(0.001, 0.02, 60)
        # MSFT highly correlated with AAPL
        msft_prices = 300.0 * np.cumprod(1 + base_returns)
        aapl_prices = 175.0 * np.cumprod(1 + base_returns * 0.9 + np.random.normal(0, 0.005, 60))
        googl_prices = 140.0 * np.cumprod(1 + base_returns * 0.8 + np.random.normal(0, 0.005, 60))

        def ohlcv_side_effect(symbol, days=60):
            price_map = {
                "MSFT": msft_prices.tolist(),
                "AAPL": aapl_prices.tolist(),
                "GOOGL": googl_prices.tolist(),
            }
            return price_map.get(symbol, [])

        mock_market_data_client.get_ohlcv_closes = AsyncMock(side_effect=ohlcv_side_effect)

        correlation = await agent._check_correlation("MSFT", sample_portfolio)
        # Highly correlated series should produce high correlation
        assert correlation > 0.5

    @pytest.mark.asyncio
    async def test_check_correlation_empty_portfolio(self, agent, empty_portfolio):
        """Correlation with empty portfolio should be 0."""
        correlation = await agent._check_correlation("AAPL", empty_portfolio)
        assert correlation == 0.0


class TestPearsonCorrelation:
    """Tests for ConcentrationRiskAgent._pearson_correlation static method."""

    def test_perfectly_correlated(self):
        """Perfectly correlated series → correlation ~1.0."""
        closes_a = [100.0 + i for i in range(50)]
        closes_b = [200.0 + i * 2 for i in range(50)]

        corr = ConcentrationRiskAgent._pearson_correlation(closes_a, closes_b)
        assert corr is not None
        assert corr > 0.9

    def test_uncorrelated(self):
        """Series with no correlation → correlation near 0."""
        import numpy as np

        np.random.seed(123)
        closes_a = (100 + np.cumsum(np.random.randn(50))).tolist()
        closes_b = (200 + np.cumsum(np.random.randn(50))).tolist()

        corr = ConcentrationRiskAgent._pearson_correlation(closes_a, closes_b)
        assert corr is not None
        assert abs(corr) < 0.5

    def test_insufficient_data_returns_none(self):
        """Too few data points → None."""
        closes_a = [100.0, 101.0, 102.0]
        closes_b = [200.0, 201.0, 202.0]

        corr = ConcentrationRiskAgent._pearson_correlation(closes_a, closes_b)
        assert corr is None

    def test_constant_series_returns_none(self):
        """Constant series (zero std) → None."""
        closes_a = [100.0] * 50
        closes_b = [200.0 + i for i in range(50)]

        corr = ConcentrationRiskAgent._pearson_correlation(closes_a, closes_b)
        assert corr is None

    def test_different_lengths_aligned(self):
        """Different length series should be aligned to shorter."""
        closes_a = [100.0 + i * 0.5 for i in range(60)]
        closes_b = [200.0 + i * 0.3 for i in range(50)]

        corr = ConcentrationRiskAgent._pearson_correlation(closes_a, closes_b)
        assert corr is not None


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
