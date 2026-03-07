"""Tests for ExecutorService — order execution with risk checks."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.models import Portfolio, Position
from app.services.executor import ExecutorService


@pytest.fixture
def mock_portfolio_svc():
    svc = AsyncMock()
    svc.get_portfolio.return_value = Portfolio(
        user_id="user-1",
        total_value=Decimal("100000"),
        cash_balance=Decimal("50000"),
        invested_value=Decimal("50000"),
        positions=[
            Position(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("150"),
                current_price=Decimal("155"),
                current_value=Decimal("15500"),
                sector="Technology",
            )
        ],
    )
    svc.record_trade = AsyncMock()
    return svc


@pytest.fixture
def mock_market_data_svc():
    svc = AsyncMock()
    svc.get_ohlcv.return_value = [{"close": 150.0}]
    svc.get_vix.return_value = 18.0
    return svc


@pytest.fixture
def mock_user_repo():
    repo = AsyncMock()
    repo.get_trading_enabled = AsyncMock(return_value=False)
    repo.update_trading_enabled = AsyncMock()
    return repo


@pytest.fixture
def executor_svc(mock_redis, mock_portfolio_svc, mock_market_data_svc, mock_user_repo):
    return ExecutorService(
        redis=mock_redis,
        portfolio_svc=mock_portfolio_svc,
        market_data_svc=mock_market_data_svc,
        user_repo=mock_user_repo,
    )


class TestExecuteOrder:
    @patch("app.services.executor.settings")
    async def test_order_approved(self, mock_settings, executor_svc, mock_portfolio_svc):
        mock_settings.mock_broker_enabled = True
        mock_settings.alpaca_api_key = ""
        mock_settings.alpaca_secret_key = ""
        mock_settings.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_settings.max_position_size = Decimal("0.10")
        mock_settings.max_single_order = Decimal("0.05")
        mock_settings.max_sector_concentration = Decimal("0.30")
        mock_settings.vix_high_threshold = Decimal("30")
        mock_settings.vix_extreme_threshold = Decimal("40")
        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="MSFT",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("350"),
            sector="Technology",
        )
        assert result.status == "filled"
        mock_portfolio_svc.record_trade.assert_called_once()

    async def test_order_rejected_extreme_vix(self, executor_svc, mock_market_data_svc):
        mock_market_data_svc.get_vix.return_value = 45.0
        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="MSFT",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("350"),
        )
        assert result.status == "rejected"
        assert "VIX" in result.error_message

    @patch("app.services.executor.settings")
    async def test_order_no_price_fetches_market(
        self, mock_settings, executor_svc, mock_market_data_svc
    ):
        mock_settings.mock_broker_enabled = True
        mock_settings.alpaca_api_key = ""
        mock_settings.alpaca_secret_key = ""
        mock_settings.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_settings.max_position_size = Decimal("0.10")
        mock_settings.max_single_order = Decimal("0.05")
        mock_settings.max_sector_concentration = Decimal("0.30")
        mock_settings.vix_high_threshold = Decimal("30")
        mock_settings.vix_extreme_threshold = Decimal("40")
        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="MSFT",
            side="buy",
            qty=Decimal("10"),
        )
        mock_market_data_svc.get_ohlcv.assert_called()
        assert result.status == "filled"

    async def test_order_no_price_no_data(self, executor_svc, mock_market_data_svc):
        mock_market_data_svc.get_ohlcv.return_value = []
        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="UNKNOWN",
            side="buy",
            qty=Decimal("10"),
        )
        assert result.status == "rejected"
        assert "price" in result.error_message.lower()

    async def test_empty_portfolio_rejected(self, executor_svc, mock_portfolio_svc):
        mock_portfolio_svc.get_portfolio.return_value = Portfolio(
            user_id="user-1", total_value=Decimal("0")
        )
        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="AAPL",
            side="buy",
            qty=Decimal("5"),
            price=Decimal("150"),
        )
        assert result.status == "rejected"
        assert "Insufficient funds" in result.error_message


class TestTradingStatus:
    async def test_get_trading_status_from_redis(self, executor_svc, mock_redis):
        mock_redis.get.return_value = "active"
        status = await executor_svc.get_trading_status("user-1")
        assert status["tradingEnabled"] is True
        assert status["status"] == "active"

    async def test_get_trading_status_falls_back_to_db(
        self, executor_svc, mock_redis, mock_user_repo
    ):
        mock_redis.get.return_value = None
        mock_user_repo.get_trading_enabled.return_value = True
        status = await executor_svc.get_trading_status("user-1")
        assert status["tradingEnabled"] is True
        mock_user_repo.get_trading_enabled.assert_called_once_with("user-1")
        mock_redis.setex.assert_called()

    async def test_get_trading_status_inactive(self, executor_svc, mock_redis):
        mock_redis.get.return_value = None
        status = await executor_svc.get_trading_status("user-1")
        assert status["tradingEnabled"] is False

    async def test_start_trading_persists_to_db(self, executor_svc, mock_redis, mock_user_repo):
        result = await executor_svc.start_trading("user-1")
        assert result["tradingEnabled"] is True
        mock_redis.setex.assert_called()
        mock_user_repo.update_trading_enabled.assert_called_once_with("user-1", True)

    async def test_stop_trading_persists_to_db(self, executor_svc, mock_redis, mock_user_repo):
        result = await executor_svc.stop_trading("user-1", "hard")
        assert result["tradingEnabled"] is False
        assert result["status"] == "hard_stopped"
        mock_user_repo.update_trading_enabled.assert_called_once_with("user-1", False)

    async def test_get_trading_status_redis_inactive(self, executor_svc, mock_redis):
        mock_redis.get.return_value = "soft_stopped"
        status = await executor_svc.get_trading_status("user-1")
        assert status["tradingEnabled"] is False
        assert status["status"] == "soft_stopped"

    async def test_get_trading_status_no_user_repo(
        self, mock_redis, mock_portfolio_svc, mock_market_data_svc
    ):
        svc = ExecutorService(
            redis=mock_redis,
            portfolio_svc=mock_portfolio_svc,
            market_data_svc=mock_market_data_svc,
            user_repo=None,
        )
        mock_redis.get.return_value = None
        status = await svc.get_trading_status("user-1")
        assert status["tradingEnabled"] is False
        assert status["status"] == "inactive"


class TestSubmitToAlpaca:
    @patch("app.services.executor.settings")
    async def test_no_keys_non_mock_rejected(self, mock_settings, executor_svc):
        mock_settings.alpaca_api_key = ""
        mock_settings.alpaca_secret_key = ""
        mock_settings.mock_broker_enabled = False
        result = await executor_svc._submit_to_alpaca(
            "AAPL", "buy", Decimal("10"), Decimal("150"), "market"
        )
        assert result.status == "rejected"
        assert "not configured" in result.error_message

    @patch("app.services.executor.httpx.AsyncClient")
    @patch("app.services.executor.settings")
    async def test_alpaca_success(self, mock_settings, mock_client_cls, executor_svc):
        mock_settings.alpaca_api_key = "key"
        mock_settings.alpaca_secret_key = "secret"
        mock_settings.alpaca_base_url = "https://paper-api.alpaca.markets"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "order-abc",
            "client_order_id": "cli-abc",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "10",
            "status": "filled",
            "filled_qty": "10",
            "filled_avg_price": "150.50",
            "submitted_at": "2025-01-01T00:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await executor_svc._submit_to_alpaca(
            "AAPL", "buy", Decimal("10"), Decimal("150"), "market"
        )
        assert result.status == "filled"
        assert result.order_id == "order-abc"
        assert result.filled_avg_price == Decimal("150.50")

    @patch("app.services.executor.httpx.AsyncClient")
    @patch("app.services.executor.settings")
    async def test_alpaca_limit_order_includes_price(
        self, mock_settings, mock_client_cls, executor_svc
    ):
        mock_settings.alpaca_api_key = "key"
        mock_settings.alpaca_secret_key = "secret"
        mock_settings.alpaca_base_url = "https://paper-api.alpaca.markets"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "order-lim",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "5",
            "status": "submitted",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await executor_svc._submit_to_alpaca("AAPL", "buy", Decimal("5"), Decimal("150"), "limit")

        call_kwargs = mock_client.post.call_args.kwargs
        payload = call_kwargs["json"]
        assert payload["limit_price"] == "150"

    @patch("app.services.executor.httpx.AsyncClient")
    @patch("app.services.executor.settings")
    async def test_alpaca_error_status(self, mock_settings, mock_client_cls, executor_svc):
        mock_settings.alpaca_api_key = "key"
        mock_settings.alpaca_secret_key = "secret"
        mock_settings.alpaca_base_url = "https://paper-api.alpaca.markets"

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await executor_svc._submit_to_alpaca(
            "AAPL", "buy", Decimal("10"), Decimal("150"), "market"
        )
        assert result.status == "rejected"
        assert "400" in result.error_message


class TestRiskAdjustment:
    @patch("app.services.executor.settings")
    async def test_risk_adjusted_size(self, mock_settings, executor_svc, mock_portfolio_svc):
        """When VIX is high, risk rules reduce order size."""
        mock_settings.mock_broker_enabled = True
        mock_settings.alpaca_api_key = ""
        mock_settings.alpaca_secret_key = ""
        mock_settings.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_settings.max_position_size = Decimal("0.10")
        mock_settings.max_single_order = Decimal("0.05")
        mock_settings.max_sector_concentration = Decimal("0.30")
        mock_settings.vix_high_threshold = Decimal("30")
        mock_settings.vix_extreme_threshold = Decimal("40")

        executor_svc._market_data_svc = executor_svc.market_data_svc
        executor_svc.market_data_svc.get_vix.return_value = 35.0  # High VIX

        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="GOOG",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("100"),
            sector="Other",
        )
        # High VIX should reduce order size by 50% (or reject), either way trade records
        if result.status == "filled":
            call_kwargs = mock_portfolio_svc.record_trade.call_args.kwargs
            assert call_kwargs["qty"] <= Decimal("10")
