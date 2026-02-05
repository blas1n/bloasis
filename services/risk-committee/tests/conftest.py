"""Test fixtures for Risk Committee Service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import OrderRequest, Portfolio, PortfolioPosition


@pytest.fixture
def mock_portfolio_client():
    """Create mock Portfolio client."""
    client = AsyncMock()
    client.get_positions = AsyncMock(
        return_value=Portfolio(
            user_id="test-user",
            total_value=100000.0,
            positions=[
                PortfolioPosition(
                    symbol="AAPL",
                    quantity=50,
                    market_value=8750.0,
                    sector="Technology",
                ),
                PortfolioPosition(
                    symbol="GOOGL",
                    quantity=20,
                    market_value=2800.0,
                    sector="Technology",
                ),
            ],
        )
    )
    client.connect = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_market_data_client():
    """Create mock Market Data client."""
    client = AsyncMock()
    client.get_vix = AsyncMock(return_value=20.0)
    client.get_average_volume = AsyncMock(return_value=5000000.0)
    client.connect = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_event_publisher():
    """Create mock Event publisher."""
    publisher = AsyncMock()
    publisher.publish_risk_decision = AsyncMock()
    publisher.connect = AsyncMock()
    publisher.close = AsyncMock()
    return publisher


@pytest.fixture
def sample_order():
    """Create a sample order request."""
    return OrderRequest(
        user_id="test-user",
        symbol="NVDA",
        action="buy",
        size=10,
        price=500.0,
        order_type="market",
    )


@pytest.fixture
def sample_portfolio():
    """Create a sample portfolio."""
    return Portfolio(
        user_id="test-user",
        total_value=100000.0,
        positions=[
            PortfolioPosition(
                symbol="AAPL",
                quantity=50,
                market_value=8750.0,
                sector="Technology",
            ),
            PortfolioPosition(
                symbol="GOOGL",
                quantity=20,
                market_value=2800.0,
                sector="Technology",
            ),
        ],
    )


@pytest.fixture
def empty_portfolio():
    """Create an empty portfolio."""
    return Portfolio(
        user_id="test-user",
        total_value=0.0,
        positions=[],
    )


@pytest.fixture
def large_order():
    """Create a large order that exceeds limits."""
    return OrderRequest(
        user_id="test-user",
        symbol="AAPL",
        action="buy",
        size=100,
        price=200.0,  # $20,000 = 20% of $100,000 portfolio
        order_type="market",
    )


@pytest.fixture
def mock_grpc_context():
    """Create mock gRPC context."""
    context = MagicMock()
    context.abort = AsyncMock()
    return context
