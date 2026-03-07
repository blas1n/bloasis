"""Tests for PortfolioService — positions, P&L, trade history, Alpaca sync."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
def portfolio_svc(
    mock_redis, mock_portfolio_repo, mock_trade_repo, mock_market_data_svc, mock_user_repo
):
    return PortfolioService(
        redis=mock_redis,
        portfolio_repo=mock_portfolio_repo,
        trade_repo=mock_trade_repo,
        market_data_svc=mock_market_data_svc,
        user_repo=mock_user_repo,
    )


def _make_position_row(symbol="AAPL", qty=10, avg_cost=150.0, current_price=160.0):
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
        # AAPL: (160-155)*10=50, MSFT: (310-155)*5=775
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


class TestSyncWithAlpaca:
    async def test_no_credentials_returns_error(self, portfolio_svc):
        with patch.object(portfolio_svc, "_get_alpaca_credentials", return_value=("", "")):
            result = await portfolio_svc.sync_with_alpaca("user-1")
        assert result["success"] is False
        assert "not configured" in result["errorMessage"]

    async def test_syncs_positions_from_alpaca(
        self, portfolio_svc, mock_portfolio_repo, mock_redis
    ):
        mock_portfolio_repo.get_positions.return_value = []

        mock_acct_resp = MagicMock()
        mock_acct_resp.status_code = 200
        mock_acct_resp.json.return_value = {"cash": "10000.00"}

        mock_pos_resp = MagicMock()
        mock_pos_resp.status_code = 200
        mock_pos_resp.json.return_value = [
            {"symbol": "AAPL", "qty": "10", "avg_entry_price": "150.00", "current_price": "160.00"},
            {"symbol": "MSFT", "qty": "5", "avg_entry_price": "300.00", "current_price": "310.00"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[mock_acct_resp, mock_pos_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(portfolio_svc, "_get_alpaca_credentials", return_value=("key", "secret")):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await portfolio_svc.sync_with_alpaca("user-1")

        assert result["success"] is True
        assert result["positionsSynced"] == 2
        assert mock_portfolio_repo.upsert_position.call_count == 2
        mock_portfolio_repo.update_cash_balance.assert_called_once_with(
            "user-1", Decimal("10000.00")
        )
        mock_redis.delete.assert_called_with("user:user-1:portfolio")

    async def test_deletes_stale_positions(self, portfolio_svc, mock_portfolio_repo):
        stale_pos = MagicMock()
        stale_pos.symbol = "GOOG"
        mock_portfolio_repo.get_positions.return_value = [stale_pos]

        mock_acct_resp = MagicMock()
        mock_acct_resp.status_code = 200
        mock_acct_resp.json.return_value = {"cash": "5000.00"}

        mock_pos_resp = MagicMock()
        mock_pos_resp.status_code = 200
        mock_pos_resp.json.return_value = [
            {"symbol": "AAPL", "qty": "10", "avg_entry_price": "150.00", "current_price": "160.00"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[mock_acct_resp, mock_pos_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(portfolio_svc, "_get_alpaca_credentials", return_value=("key", "secret")):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await portfolio_svc.sync_with_alpaca("user-1")

        assert result["success"] is True
        mock_portfolio_repo.delete_position.assert_called_once_with("user-1", "GOOG")

    async def test_alpaca_api_error(self, portfolio_svc):
        import httpx

        mock_acct_resp = MagicMock()
        mock_acct_resp.status_code = 401
        mock_acct_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_acct_resp
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_acct_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(portfolio_svc, "_get_alpaca_credentials", return_value=("key", "secret")):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await portfolio_svc.sync_with_alpaca("user-1")

        assert result["success"] is False


class TestGetAlpacaCredentials:
    async def test_uses_user_broker_config(self, portfolio_svc, mock_user_repo):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        f = Fernet(key)

        cfg_api = MagicMock()
        cfg_api.config_key = "api_key"
        cfg_api.encrypted_value = f.encrypt(b"user-api-key").decode()

        cfg_secret = MagicMock()
        cfg_secret.config_key = "secret_key"
        cfg_secret.encrypted_value = f.encrypt(b"user-secret").decode()

        mock_user_repo.get_broker_config.return_value = [cfg_api, cfg_secret]

        with patch("app.shared.utils.broker.settings") as mock_settings:
            mock_settings.fernet_key = key.decode()
            mock_settings.alpaca_api_key = "global-key"
            mock_settings.alpaca_secret_key = "global-secret"
            api_key, secret_key = await portfolio_svc._get_alpaca_credentials("user-1")

        assert api_key == "user-api-key"
        assert secret_key == "user-secret"

    async def test_falls_back_to_global(self, portfolio_svc, mock_user_repo):
        mock_user_repo.get_broker_config.return_value = []

        with patch("app.services.portfolio.settings") as mock_settings:
            mock_settings.alpaca_api_key = "global-key"
            mock_settings.alpaca_secret_key = "global-secret"
            api_key, secret_key = await portfolio_svc._get_alpaca_credentials("user-1")

        assert api_key == "global-key"
        assert secret_key == "global-secret"
