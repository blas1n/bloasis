"""Tests for OrderProcessor — outbox consumer, polling, and reconciliation."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.models import BrokerPosition, OrderResult, OrderSide, OrderStatus
from app.services.order_processor import OrderProcessor

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def mock_order_repo():
    return AsyncMock()


@pytest.fixture
def mock_user_repo():
    return AsyncMock()


@pytest.fixture
def mock_portfolio_svc():
    return AsyncMock()


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def processor(mock_order_repo, mock_user_repo, mock_portfolio_svc, mock_redis):
    return OrderProcessor(
        order_repo=mock_order_repo,
        user_repo=mock_user_repo,
        portfolio_svc=mock_portfolio_svc,
        redis=mock_redis,
    )


def _make_order(
    status: str = "pending",
    retry_count: int = 0,
    max_retries: int = 3,
    broker_order_id: str | None = None,
) -> MagicMock:
    order = MagicMock()
    order.id = uuid.uuid4()
    order.user_id = TEST_USER_ID
    order.client_order_id = f"client-{uuid.uuid4()}"
    order.broker_order_id = broker_order_id
    order.broker_type = "alpaca"
    order.symbol = "AAPL"
    order.side = "buy"
    order.qty = Decimal("10")
    order.price = Decimal("150")
    order.order_type = "market"
    order.ai_reason = "Test reason"
    order.status = status
    order.retry_count = retry_count
    order.max_retries = max_retries
    return order


class TestProcessPendingOrders:
    async def test_no_pending_orders(self, processor, mock_order_repo):
        mock_order_repo.get_pending_orders.return_value = []
        count = await processor.process_pending_orders()
        assert count == 0

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_submits_pending_order(
        self, mock_factory, processor, mock_order_repo, mock_portfolio_svc
    ):
        order = _make_order()
        mock_order_repo.get_pending_orders.return_value = [order]

        mock_broker = AsyncMock()
        mock_broker.submit_order.return_value = OrderResult(
            order_id="broker-123",
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=Decimal("10"),
            status=OrderStatus.FILLED,
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.50"),
        )
        mock_factory.return_value = mock_broker

        count = await processor.process_pending_orders()

        assert count == 1
        mock_order_repo.update_status.assert_called()
        mock_portfolio_svc.record_trade.assert_awaited_once()

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_max_retries_exceeded(self, mock_factory, processor, mock_order_repo):
        order = _make_order(retry_count=3, max_retries=3)
        mock_order_repo.get_pending_orders.return_value = [order]

        count = await processor.process_pending_orders()

        assert count == 0
        mock_order_repo.update_status.assert_awaited_once_with(
            order.id, OrderStatus.FAILED, error_message="Max retries exceeded"
        )

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_broker_exception_increments_retry(
        self, mock_factory, processor, mock_order_repo
    ):
        order = _make_order()
        mock_order_repo.get_pending_orders.return_value = [order]

        mock_broker = AsyncMock()
        mock_broker.submit_order.side_effect = Exception("Connection refused")
        mock_factory.return_value = mock_broker

        count = await processor.process_pending_orders()

        assert count == 0
        mock_order_repo.increment_retry.assert_awaited_once()
        call_args = mock_order_repo.increment_retry.await_args
        assert call_args.args[0] == order.id
        assert "Connection refused" in call_args.kwargs.get("error_message", "")


class TestPollUnresolvedOrders:
    async def test_no_unresolved_orders(self, processor, mock_order_repo):
        mock_order_repo.get_unresolved_orders.return_value = []
        count = await processor.poll_unresolved_orders()
        assert count == 0

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_resolves_filled_order(
        self, mock_factory, processor, mock_order_repo, mock_portfolio_svc
    ):
        order = _make_order(status="submitted", broker_order_id="broker-123")
        mock_order_repo.get_unresolved_orders.return_value = [order]

        mock_broker = AsyncMock()
        mock_broker.get_order_status.return_value = OrderResult(
            order_id="broker-123",
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=Decimal("10"),
            status=OrderStatus.FILLED,
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.50"),
        )
        mock_factory.return_value = mock_broker

        count = await processor.poll_unresolved_orders()

        assert count == 1
        mock_portfolio_svc.record_trade.assert_awaited_once()

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_resolves_cancelled_order(self, mock_factory, processor, mock_order_repo):
        order = _make_order(status="submitted", broker_order_id="broker-123")
        mock_order_repo.get_unresolved_orders.return_value = [order]

        mock_broker = AsyncMock()
        mock_broker.get_order_status.return_value = OrderResult(
            order_id="broker-123",
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=Decimal("10"),
            status=OrderStatus.CANCELLED,
        )
        mock_factory.return_value = mock_broker

        count = await processor.poll_unresolved_orders()

        assert count == 1
        mock_order_repo.update_status.assert_awaited_with(order.id, OrderStatus.CANCELLED)

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_skips_order_without_broker_id(self, mock_factory, processor, mock_order_repo):
        order = _make_order(status="submitted", broker_order_id=None)
        mock_order_repo.get_unresolved_orders.return_value = [order]

        count = await processor.poll_unresolved_orders()

        assert count == 0
        mock_factory.assert_not_called()


class TestReconcileWithBroker:
    async def test_no_active_users(self, processor, mock_user_repo):
        mock_user_repo.get_active_trading_users.return_value = []
        diffs = await processor.reconcile_with_broker()
        assert diffs == 0

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_no_diffs(self, mock_factory, processor, mock_user_repo, mock_portfolio_svc):
        mock_user_repo.get_active_trading_users.return_value = [TEST_USER_ID]

        aapl_position = MagicMock()
        aapl_position.symbol = "AAPL"
        aapl_position.quantity = Decimal("10")

        mock_broker = AsyncMock()
        mock_broker.get_positions.return_value = [
            BrokerPosition(
                symbol="AAPL",
                quantity=Decimal("10"),
                avg_entry_price=Decimal("150"),
                current_price=Decimal("155"),
                market_value=Decimal("1550"),
            )
        ]
        mock_factory.return_value = mock_broker
        mock_portfolio_svc.get_positions.return_value = [aapl_position]

        diffs = await processor.reconcile_with_broker()
        assert diffs == 0

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_detects_quantity_mismatch(
        self, mock_factory, processor, mock_user_repo, mock_portfolio_svc
    ):
        mock_user_repo.get_active_trading_users.return_value = [TEST_USER_ID]

        db_position = MagicMock()
        db_position.symbol = "AAPL"
        db_position.quantity = Decimal("10")

        mock_broker = AsyncMock()
        mock_broker.get_positions.return_value = [
            BrokerPosition(
                symbol="AAPL",
                quantity=Decimal("15"),
                avg_entry_price=Decimal("150"),
                current_price=Decimal("155"),
                market_value=Decimal("2325"),
            )
        ]
        mock_factory.return_value = mock_broker
        mock_portfolio_svc.get_positions.return_value = [db_position]

        diffs = await processor.reconcile_with_broker()
        assert diffs == 1
        processor.redis.setex.assert_awaited_once()
        redis_key = processor.redis.setex.await_args.args[0]
        assert f"reconciliation:diffs:{TEST_USER_ID}" == redis_key

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_detects_broker_only_position(
        self, mock_factory, processor, mock_user_repo, mock_portfolio_svc
    ):
        mock_user_repo.get_active_trading_users.return_value = [TEST_USER_ID]

        mock_broker = AsyncMock()
        mock_broker.get_positions.return_value = [
            BrokerPosition(
                symbol="TSLA",
                quantity=Decimal("5"),
                avg_entry_price=Decimal("200"),
                current_price=Decimal("210"),
                market_value=Decimal("1050"),
            )
        ]
        mock_factory.return_value = mock_broker
        mock_portfolio_svc.get_positions.return_value = []

        diffs = await processor.reconcile_with_broker()
        assert diffs == 1
        processor.redis.setex.assert_awaited_once()
        redis_key = processor.redis.setex.await_args.args[0]
        assert f"reconciliation:diffs:{TEST_USER_ID}" == redis_key

    @patch("app.services.order_processor.create_broker_adapter")
    async def test_handles_broker_adapter_error(self, mock_factory, processor, mock_user_repo):
        mock_user_repo.get_active_trading_users.return_value = [TEST_USER_ID]
        mock_factory.side_effect = ValueError("No credentials")

        diffs = await processor.reconcile_with_broker()
        assert diffs == 0
