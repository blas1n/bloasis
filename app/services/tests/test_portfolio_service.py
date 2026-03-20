"""Tests for PortfolioService — positions, P&L, trade history, broker sync."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.models import BrokerAccountInfo, BrokerPosition
from app.services.portfolio import PortfolioService


@pytest.fixture
def mock_portfolio_repo():
    return AsyncMock()


@pytest.fixture
def mock_trade_repo():
    return AsyncMock()


@pytest.fixture
def mock_market_data_svc():
    svc = AsyncMock()
    svc.get_previous_close = AsyncMock(return_value=Decimal("155.00"))
    return svc


@pytest.fixture
def portfolio_svc(mock_redis, mock_portfolio_repo, mock_trade_repo, mock_market_data_svc):
    return PortfolioService(
        redis=mock_redis,
        portfolio_repo=mock_portfolio_repo,
        trade_repo=mock_trade_repo,
        market_data_svc=mock_market_data_svc,
    )


def _make_position_row(
    symbol: str = "AAPL",
    qty: int = 10,
    avg_cost: float = 150.0,
    current_price: float = 160.0,
) -> MagicMock:
    row = MagicMock()
    row.symbol = symbol
    row.quantity = qty
    row.avg_cost = Decimal(str(avg_cost))
    row.current_price = Decimal(str(current_price))
    row.currency = "USD"
    return row


class TestGetPositions:
    async def test_returns_positions(self, portfolio_svc, mock_portfolio_repo):
        mock_portfolio_repo.get_positions.return_value = [
            _make_position_row("AAPL", 10, 150.0, 160.0),
            _make_position_row("MSFT", 5, 300.0, 310.0),
        ]
        positions = await portfolio_svc.get_positions("user-1")
        assert len(positions) == 2
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10
        assert positions[0].unrealized_pnl == Decimal("100.0")

    async def test_empty_positions(self, portfolio_svc, mock_portfolio_repo):
        mock_portfolio_repo.get_positions.return_value = []
        positions = await portfolio_svc.get_positions("user-1")
        assert positions == []

    async def test_pnl_percent_zero_cost(self, portfolio_svc, mock_portfolio_repo):
        mock_portfolio_repo.get_positions.return_value = [
            _make_position_row("AAPL", 10, 0.0, 160.0),
        ]
        positions = await portfolio_svc.get_positions("user-1")
        assert positions[0].unrealized_pnl_percent == 0.0

    async def test_daily_pnl_calculated(
        self, portfolio_svc, mock_portfolio_repo, mock_market_data_svc
    ):
        """Daily P&L: (160 - 155) * 10 = 50."""
        mock_market_data_svc.get_previous_close.return_value = Decimal("155.00")
        mock_portfolio_repo.get_positions.return_value = [
            _make_position_row("AAPL", 10, 150.0, 160.0),
        ]
        positions = await portfolio_svc.get_positions("user-1")
        assert positions[0].daily_pnl == Decimal("50.0")
        assert positions[0].daily_pnl_pct > 0

    async def test_daily_pnl_without_market_data(
        self, mock_redis, mock_portfolio_repo, mock_trade_repo
    ):
        """Without market_data_svc, daily_pnl defaults to 0."""
        svc = PortfolioService(
            redis=mock_redis, portfolio_repo=mock_portfolio_repo, trade_repo=mock_trade_repo
        )
        mock_portfolio_repo.get_positions.return_value = [
            _make_position_row("AAPL", 10, 150.0, 160.0),
        ]
        positions = await svc.get_positions("user-1")
        assert positions[0].daily_pnl == Decimal("0")

    async def test_daily_pnl_aggregated_in_portfolio(
        self, portfolio_svc, mock_redis, mock_portfolio_repo, mock_market_data_svc
    ):
        """Portfolio-level daily_pnl is the sum of position daily P&Ls."""
        mock_redis.get.return_value = None
        mock_market_data_svc.get_previous_close.return_value = Decimal("155.00")
        mock_portfolio_repo.get_positions.return_value = [
            _make_position_row("AAPL", 10, 150.0, 160.0),
            _make_position_row("MSFT", 5, 300.0, 310.0),
        ]
        mock_portfolio_repo.get_cash_balance.return_value = Decimal("5000")
        portfolio = await portfolio_svc.get_portfolio("user-1")
        assert portfolio.daily_pnl > Decimal("0")

    async def test_daily_pnl_pct_zero_total_value(
        self, portfolio_svc, mock_redis, mock_portfolio_repo
    ):
        """daily_pnl_pct should be 0 when total_value is 0."""
        mock_redis.get.return_value = None
        mock_portfolio_repo.get_positions.return_value = []
        mock_portfolio_repo.get_cash_balance.return_value = Decimal("0")
        portfolio = await portfolio_svc.get_portfolio("user-1")
        assert portfolio.daily_pnl_pct == 0.0


class TestGetPortfolio:
    async def test_returns_from_cache(self, portfolio_svc, mock_redis):
        mock_redis.get.return_value = {
            "user_id": "user-1",
            "total_value": "10000",
            "cash_balance": "5000",
            "invested_value": "5000",
            "total_return": 5.0,
            "total_return_amount": "250",
            "positions": [],
            "timestamp": "2024-01-01T00:00:00",
        }
        portfolio = await portfolio_svc.get_portfolio("user-1")
        assert portfolio.user_id == "user-1"
        assert portfolio.total_value == Decimal("10000")

    async def test_computes_from_db(self, portfolio_svc, mock_redis, mock_portfolio_repo):
        mock_redis.get.return_value = None
        mock_portfolio_repo.get_positions.return_value = [
            _make_position_row("AAPL", 10, 150.0, 160.0),
        ]
        mock_portfolio_repo.get_cash_balance.return_value = Decimal("5000")

        portfolio = await portfolio_svc.get_portfolio("user-1")
        assert portfolio.cash_balance == Decimal("5000")
        assert portfolio.invested_value == Decimal("1600.0")
        assert len(portfolio.positions) == 1
        mock_redis.setex.assert_called_once()


class TestGetTrades:
    async def test_returns_trades(self, portfolio_svc, mock_trade_repo):
        row = MagicMock()
        row.order_id = "order-1"
        row.symbol = "AAPL"
        row.action = "BUY"
        row.quantity = 10
        row.price = Decimal("150.00")
        row.commission = Decimal("0")
        row.realized_pnl = Decimal("0")
        row.executed_at = datetime(2024, 1, 1, tzinfo=UTC)
        row.ai_reason = "test"
        mock_trade_repo.get_trades.return_value = [row]

        trades = await portfolio_svc.get_trades("user-1", limit=10)
        assert len(trades) == 1
        assert trades[0].symbol == "AAPL"
        assert trades[0].side == "buy"
        assert trades[0].ai_reason == "test"

    async def test_returns_trades_with_null_ai_reason(self, portfolio_svc, mock_trade_repo):
        row = MagicMock()
        row.order_id = "order-2"
        row.symbol = "TSLA"
        row.action = "SELL"
        row.quantity = 5
        row.price = Decimal("200.00")
        row.commission = Decimal("1.00")
        row.realized_pnl = Decimal("50.00")
        row.executed_at = datetime(2024, 1, 2, tzinfo=UTC)
        row.ai_reason = None
        mock_trade_repo.get_trades.return_value = [row]

        trades = await portfolio_svc.get_trades("user-1", limit=10)
        assert len(trades) == 1
        assert trades[0].ai_reason is None

    async def test_empty_trades(self, portfolio_svc, mock_trade_repo):
        mock_trade_repo.get_trades.return_value = []
        trades = await portfolio_svc.get_trades("user-1")
        assert trades == []


class TestRecordTrade:
    async def test_records_and_invalidates_cache(self, portfolio_svc, mock_trade_repo, mock_redis):
        await portfolio_svc.record_trade(
            user_id="user-1",
            order_id="order-1",
            symbol="AAPL",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("150"),
            ai_reason="test",
        )
        mock_trade_repo.record_trade_and_update_position.assert_called_once()
        mock_redis.delete.assert_called_once_with("user:user-1:portfolio")


class TestSyncWithBroker:
    async def test_syncs_positions(self, portfolio_svc, mock_portfolio_repo, mock_redis):
        mock_portfolio_repo.get_positions.return_value = []

        mock_broker = AsyncMock()
        mock_broker.get_account.return_value = BrokerAccountInfo(
            equity=Decimal("15000"), cash=Decimal("10000"), buying_power=Decimal("10000")
        )
        mock_broker.get_positions.return_value = [
            BrokerPosition(
                symbol="AAPL",
                quantity=Decimal("10"),
                avg_entry_price=Decimal("150"),
                current_price=Decimal("160"),
                market_value=Decimal("1600"),
            ),
            BrokerPosition(
                symbol="MSFT",
                quantity=Decimal("5"),
                avg_entry_price=Decimal("300"),
                current_price=Decimal("310"),
                market_value=Decimal("1550"),
            ),
        ]

        result = await portfolio_svc.sync_with_broker("user-1", mock_broker)
        assert result["success"] is True
        assert result["positionsSynced"] == 2
        assert mock_portfolio_repo.upsert_position.call_count == 2
        mock_portfolio_repo.update_cash_balance.assert_called_once_with("user-1", Decimal("10000"))
        mock_redis.delete.assert_called_with("user:user-1:portfolio")

    async def test_deletes_stale_positions(self, portfolio_svc, mock_portfolio_repo):
        stale_pos = MagicMock()
        stale_pos.symbol = "GOOG"
        mock_portfolio_repo.get_positions.return_value = [stale_pos]

        mock_broker = AsyncMock()
        mock_broker.get_account.return_value = BrokerAccountInfo(
            equity=Decimal("5000"), cash=Decimal("5000"), buying_power=Decimal("5000")
        )
        mock_broker.get_positions.return_value = [
            BrokerPosition(
                symbol="AAPL",
                quantity=Decimal("10"),
                avg_entry_price=Decimal("150"),
                current_price=Decimal("160"),
                market_value=Decimal("1600"),
            ),
        ]

        result = await portfolio_svc.sync_with_broker("user-1", mock_broker)
        assert result["success"] is True
        mock_portfolio_repo.delete_position.assert_called_once_with("user-1", "GOOG")

    async def test_broker_api_error(self, portfolio_svc):
        mock_broker = AsyncMock()
        mock_broker.get_account.side_effect = Exception("Connection failed")

        result = await portfolio_svc.sync_with_broker("user-1", mock_broker)
        assert result["success"] is False
        assert "connection" in result["errorMessage"].lower()
