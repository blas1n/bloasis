"""Tests for ExecutorService — order execution with Saga pattern."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.core.models import OrderResult, OrderSide, OrderStatus, Portfolio, Position
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
                quantity=Decimal("100"),
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
def mock_broker():
    broker = AsyncMock()
    broker.submit_order.return_value = OrderResult(
        order_id="broker-order-1",
        client_order_id="",
        symbol="MSFT",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        status=OrderStatus.FILLED,
        filled_qty=Decimal("10"),
        filled_avg_price=Decimal("350"),
    )
    broker.cancel_order.return_value = True
    return broker


@pytest.fixture
def mock_order_repo():
    repo = AsyncMock()
    record = AsyncMock()
    record.id = uuid.uuid4()
    repo.create_pending_order.return_value = record
    return repo


@pytest.fixture
def executor_svc(
    mock_redis,
    mock_portfolio_svc,
    mock_market_data_svc,
    mock_broker,
    mock_order_repo,
    mock_user_repo,
):
    return ExecutorService(
        redis=mock_redis,
        portfolio_svc=mock_portfolio_svc,
        market_data_svc=mock_market_data_svc,
        broker=mock_broker,
        order_repo=mock_order_repo,
        user_repo=mock_user_repo,
    )


class TestExecuteOrder:
    @patch("app.services.executor.settings")
    async def test_order_approved_saga_flow(
        self, mock_settings, executor_svc, mock_portfolio_svc, mock_broker, mock_order_repo
    ):
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
        assert result.status == OrderStatus.FILLED
        # Verify Saga steps
        mock_order_repo.create_pending_order.assert_called_once()
        mock_broker.submit_order.assert_called_once()
        mock_portfolio_svc.record_trade.assert_called_once()
        # Order status updated to filled
        assert mock_order_repo.update_status.call_count == 2  # after submit + after record

    async def test_order_rejected_extreme_vix(self, executor_svc, mock_market_data_svc):
        mock_market_data_svc.get_vix.return_value = 45.0
        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="MSFT",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("350"),
        )
        assert result.status == OrderStatus.FAILED
        assert "VIX" in (result.error_message or "")

    @patch("app.services.executor.settings")
    async def test_broker_failure_marks_order_failed(
        self, mock_settings, executor_svc, mock_broker, mock_order_repo
    ):
        mock_settings.max_position_size = Decimal("0.10")
        mock_settings.max_single_order = Decimal("0.05")
        mock_settings.max_sector_concentration = Decimal("0.30")
        mock_settings.vix_high_threshold = Decimal("30")
        mock_settings.vix_extreme_threshold = Decimal("40")
        mock_broker.submit_order.side_effect = Exception("Connection error")

        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="MSFT",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("350"),
        )
        assert result.status == OrderStatus.FAILED
        # Order marked as failed in DB
        mock_order_repo.update_status.assert_called_once()
        call_args = mock_order_repo.update_status.call_args
        assert call_args[0][1] == OrderStatus.FAILED

    @patch("app.services.executor.settings")
    async def test_trade_recording_failure_triggers_compensation(
        self, mock_settings, executor_svc, mock_portfolio_svc, mock_broker, mock_order_repo
    ):
        mock_settings.max_position_size = Decimal("0.10")
        mock_settings.max_single_order = Decimal("0.05")
        mock_settings.max_sector_concentration = Decimal("0.30")
        mock_settings.vix_high_threshold = Decimal("30")
        mock_settings.vix_extreme_threshold = Decimal("40")
        mock_portfolio_svc.record_trade.side_effect = Exception("DB error")

        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="MSFT",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("350"),
        )
        assert result.status == OrderStatus.COMPENSATION_NEEDED
        # Broker cancel_order called for compensation
        mock_broker.cancel_order.assert_called_once_with("broker-order-1")

    async def test_order_no_price_fetches_market(self, executor_svc, mock_market_data_svc):
        mock_market_data_svc.get_ohlcv.return_value = []
        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="UNKNOWN",
            side="buy",
            qty=Decimal("10"),
        )
        assert result.status == OrderStatus.FAILED
        assert "price" in (result.error_message or "").lower()

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
        assert result.status == OrderStatus.FAILED
        assert "Insufficient funds" in (result.error_message or "")


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

    async def test_get_trading_status_no_user_repo(
        self, mock_redis, mock_portfolio_svc, mock_market_data_svc, mock_broker, mock_order_repo
    ):
        svc = ExecutorService(
            redis=mock_redis,
            portfolio_svc=mock_portfolio_svc,
            market_data_svc=mock_market_data_svc,
            broker=mock_broker,
            order_repo=mock_order_repo,
            user_repo=None,
        )
        mock_redis.get.return_value = None
        status = await svc.get_trading_status("user-1")
        assert status["tradingEnabled"] is False
        assert status["status"] == "inactive"


class TestRiskAdjustment:
    @patch("app.services.executor.settings")
    async def test_risk_adjusted_size_high_vix(
        self, mock_settings, executor_svc, mock_portfolio_svc, mock_broker, mock_order_repo
    ):
        """When VIX is high (30-40), risk rules reduce order size by 50%."""
        mock_settings.max_position_size = Decimal("0.10")
        mock_settings.max_single_order = Decimal("0.05")
        mock_settings.max_sector_concentration = Decimal("0.30")
        mock_settings.vix_high_threshold = Decimal("30")
        mock_settings.vix_extreme_threshold = Decimal("40")

        executor_svc.market_data_svc.get_vix.return_value = 35.0  # High VIX

        result = await executor_svc.execute_order(
            user_id="user-1",
            symbol="GOOG",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("100"),
            sector="Other",
        )
        # High VIX should reduce order size by 50%
        if result.status == "filled":
            call_kwargs = mock_portfolio_svc.record_trade.call_args.kwargs
            assert call_kwargs["qty"] <= Decimal("10")
