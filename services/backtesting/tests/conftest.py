"""Pytest fixtures for Backtesting Service tests."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.clients.market_data_client import MarketDataClient
from src.engines.finrl_engine import FinRLEngine
from src.engines.vectorbt_engine import VectorBTEngine
from src.models import BacktestConfig, PortfolioMetrics, SymbolResult
from src.service import BacktestingServicer


def _generate_mock_ohlcv(days: int = 60) -> list[dict]:
    """Generate mock OHLCV data with valid dates."""
    base_date = datetime(2024, 1, 1)
    mock_ohlcv = []
    for i in range(days):
        date = base_date + timedelta(days=i)
        mock_ohlcv.append(
            {
                "timestamp": date.strftime("%Y-%m-%dT00:00:00Z"),
                "open": 150.0 + i * 0.5,
                "high": 152.0 + i * 0.5,
                "low": 148.0 + i * 0.5,
                "close": 151.0 + i * 0.5,
                "volume": 10_000_000 + i * 100_000,
                "adj_close": 151.0 + i * 0.5,
            }
        )
    return mock_ohlcv


@pytest.fixture
def mock_market_data_client():
    """Mock Market Data Service client."""
    client = AsyncMock(spec=MarketDataClient)
    client.connect = AsyncMock()
    client.close = AsyncMock()

    # Mock OHLCV data - 60 days of simulated price data with valid dates
    mock_ohlcv = _generate_mock_ohlcv(60)

    client.get_ohlcv = AsyncMock(return_value=mock_ohlcv)
    client.get_batch_ohlcv = AsyncMock(return_value={"AAPL": mock_ohlcv, "MSFT": mock_ohlcv})

    return client


@pytest.fixture
def default_backtest_config():
    """Default backtest configuration."""
    return BacktestConfig(
        initial_cash=Decimal("100000.00"),
        commission=0.001,
        slippage=0.001,
        stop_loss=0.0,
        take_profit=0.0,
    )


@pytest.fixture
def vectorbt_engine(mock_market_data_client):
    """VectorBT engine with mocked market data client."""
    return VectorBTEngine(mock_market_data_client)


@pytest.fixture
def finrl_engine(mock_market_data_client):
    """FinRL engine with mocked market data client."""
    return FinRLEngine(mock_market_data_client)


@pytest.fixture
def backtesting_servicer(mock_market_data_client):
    """Create BacktestingServicer with mocked dependencies."""
    return BacktestingServicer(market_data_client=mock_market_data_client)


@pytest.fixture
def sample_symbol_result():
    """Sample SymbolResult for testing."""
    return SymbolResult(
        symbol="AAPL",
        total_return=0.25,
        sharpe_ratio=1.5,
        sortino_ratio=2.0,
        max_drawdown=0.15,
        win_rate=0.55,
        profit_factor=1.8,
        total_trades=42,
        avg_trade_duration_days=5.5,
        calmar_ratio=1.67,
        passed=True,
    )


@pytest.fixture
def sample_portfolio_metrics():
    """Sample PortfolioMetrics for testing."""
    return PortfolioMetrics(
        total_return=0.20,
        sharpe_ratio=1.2,
        max_drawdown=0.18,
        volatility=0.05,
    )


@pytest.fixture
def mock_grpc_context():
    """Mock gRPC context for servicer tests."""
    context = AsyncMock()
    context.set_code = AsyncMock()
    context.set_details = AsyncMock()
    return context
