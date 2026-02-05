"""Tests for Executor Service."""

import pytest
from shared.generated import executor_pb2

from src.service import ExecutorServicer


class TestExecutorServicer:
    """Tests for ExecutorServicer."""

    @pytest.fixture
    def servicer(self, mock_alpaca_client, mock_event_publisher, mock_redis_client):
        """Create ExecutorServicer with mocks."""
        return ExecutorServicer(
            alpaca_client=mock_alpaca_client,
            event_publisher=mock_event_publisher,
            redis_client=mock_redis_client,
        )

    @pytest.mark.asyncio
    async def test_execute_market_order_success(
        self, servicer, mock_grpc_context, mock_redis_client
    ):
        """Test successful market order execution."""
        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            risk_approval_id="approval-123",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is True
        assert response.order_id == "order-123"
        assert response.status == "submitted"

    @pytest.mark.asyncio
    async def test_execute_limit_order_success(
        self, servicer, mock_grpc_context, mock_redis_client
    ):
        """Test successful limit order execution."""
        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="limit",
            limit_price=175.0,
            risk_approval_id="approval-123",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is True
        assert response.order_id == "order-124"

    @pytest.mark.asyncio
    async def test_execute_bracket_order_success(
        self, servicer, mock_grpc_context, mock_redis_client
    ):
        """Test successful bracket order execution."""
        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="bracket",
            stop_loss=170.0,
            take_profit=185.0,
            risk_approval_id="approval-123",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is True
        assert response.order_id == "order-125"

    @pytest.mark.asyncio
    async def test_execute_order_missing_user_id(self, servicer, mock_grpc_context):
        """Test order execution with missing user_id."""
        request = executor_pb2.ExecuteOrderRequest(
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is False
        assert "user_id" in response.error_message

    @pytest.mark.asyncio
    async def test_execute_order_missing_symbol(self, servicer, mock_grpc_context):
        """Test order execution with missing symbol."""
        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            side="buy",
            qty=10.0,
            order_type="market",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is False
        assert "symbol" in response.error_message

    @pytest.mark.asyncio
    async def test_execute_order_invalid_qty(self, servicer, mock_grpc_context):
        """Test order execution with invalid quantity."""
        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            side="buy",
            qty=-10.0,
            order_type="market",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is False
        assert "qty" in response.error_message

    @pytest.mark.asyncio
    async def test_execute_order_no_risk_approval(
        self, servicer, mock_grpc_context, mock_redis_client
    ):
        """Test order execution without risk approval."""
        mock_redis_client.exists.return_value = False

        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            risk_approval_id="invalid-approval",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is False
        assert "Risk approval" in response.error_message

    @pytest.mark.asyncio
    async def test_execute_order_unknown_type(self, servicer, mock_grpc_context):
        """Test order execution with unknown order type."""
        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="unknown",
            risk_approval_id="approval-123",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is False
        assert "Unknown order type" in response.error_message

    @pytest.mark.asyncio
    async def test_execute_limit_order_no_price(self, servicer, mock_grpc_context):
        """Test limit order without limit price."""
        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="limit",
            risk_approval_id="approval-123",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is False
        assert "limit_price" in response.error_message

    @pytest.mark.asyncio
    async def test_execute_bracket_order_no_stops(self, servicer, mock_grpc_context):
        """Test bracket order without stop_loss/take_profit."""
        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="bracket",
            risk_approval_id="approval-123",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is False
        assert "stop_loss" in response.error_message or "take_profit" in response.error_message

    @pytest.mark.asyncio
    async def test_execute_order_rejected(
        self, servicer, mock_grpc_context, mock_alpaca_client, rejected_order_result
    ):
        """Test handling of rejected order."""
        mock_alpaca_client.submit_market_order.return_value = rejected_order_result

        request = executor_pb2.ExecuteOrderRequest(
            user_id="test-user",
            symbol="INVALID",
            side="buy",
            qty=10.0,
            order_type="market",
            risk_approval_id="approval-123",
        )

        response = await servicer.ExecuteOrder(request, mock_grpc_context)

        assert response.success is False
        assert response.status == "rejected"

    @pytest.mark.asyncio
    async def test_get_order_status_success(self, servicer, mock_grpc_context, mock_alpaca_client):
        """Test getting order status."""
        request = executor_pb2.GetOrderStatusRequest(order_id="order-123")

        response = await servicer.GetOrderStatus(request, mock_grpc_context)

        assert response.order_id == "order-123"
        assert response.status == "filled"
        assert response.filled_qty == 10.0
        assert response.filled_avg_price == 175.50

    @pytest.mark.asyncio
    async def test_get_order_status_missing_id(self, servicer, mock_grpc_context):
        """Test getting order status without order_id."""
        request = executor_pb2.GetOrderStatusRequest()

        await servicer.GetOrderStatus(request, mock_grpc_context)

        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(
        self, servicer, mock_grpc_context, mock_alpaca_client
    ):
        """Test getting status of non-existent order."""
        mock_alpaca_client.get_order_status.side_effect = Exception("Order not found")

        request = executor_pb2.GetOrderStatusRequest(order_id="nonexistent")

        await servicer.GetOrderStatus(request, mock_grpc_context)

        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, servicer, mock_grpc_context, mock_event_publisher):
        """Test successful order cancellation."""
        request = executor_pb2.CancelOrderRequest(
            user_id="test-user",
            order_id="order-123",
        )

        response = await servicer.CancelOrder(request, mock_grpc_context)

        assert response.success is True
        mock_event_publisher.publish_order_cancelled.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, servicer, mock_grpc_context, mock_alpaca_client):
        """Test failed order cancellation."""
        mock_alpaca_client.cancel_order.return_value = False

        request = executor_pb2.CancelOrderRequest(
            user_id="test-user",
            order_id="order-123",
        )

        response = await servicer.CancelOrder(request, mock_grpc_context)

        assert response.success is False

    @pytest.mark.asyncio
    async def test_cancel_order_missing_id(self, servicer, mock_grpc_context):
        """Test cancel order without order_id."""
        request = executor_pb2.CancelOrderRequest(user_id="test-user")

        response = await servicer.CancelOrder(request, mock_grpc_context)

        assert response.success is False
        assert "order_id" in response.message

    @pytest.mark.asyncio
    async def test_get_account_success(self, servicer, mock_grpc_context):
        """Test getting account information."""
        request = executor_pb2.GetAccountRequest(user_id="test-user")

        response = await servicer.GetAccount(request, mock_grpc_context)

        assert response.cash == 100000.0
        assert response.buying_power == 200000.0
        assert response.portfolio_value == 150000.0
        assert response.equity == 150000.0

    @pytest.mark.asyncio
    async def test_get_account_failure(self, servicer, mock_grpc_context, mock_alpaca_client):
        """Test failed account retrieval."""
        mock_alpaca_client.get_account.side_effect = Exception("API error")

        request = executor_pb2.GetAccountRequest(user_id="test-user")

        await servicer.GetAccount(request, mock_grpc_context)

        mock_grpc_context.abort.assert_called()


class TestRiskApprovalVerification:
    """Tests for risk approval verification."""

    @pytest.fixture
    def servicer(self, mock_alpaca_client, mock_event_publisher, mock_redis_client):
        """Create ExecutorServicer with mocks."""
        return ExecutorServicer(
            alpaca_client=mock_alpaca_client,
            event_publisher=mock_event_publisher,
            redis_client=mock_redis_client,
        )

    @pytest.mark.asyncio
    async def test_verify_risk_approval_valid(self, servicer, mock_redis_client):
        """Test valid risk approval."""
        mock_redis_client.exists.return_value = True

        result = await servicer._verify_risk_approval("valid-approval")

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_risk_approval_invalid(self, servicer, mock_redis_client):
        """Test invalid risk approval."""
        mock_redis_client.exists.return_value = False

        result = await servicer._verify_risk_approval("invalid-approval")

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_risk_approval_empty(self, servicer):
        """Test empty risk approval ID."""
        result = await servicer._verify_risk_approval("")

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_risk_approval_redis_error(self, servicer, mock_redis_client):
        """Test risk approval check with Redis error."""
        mock_redis_client.exists.side_effect = Exception("Redis error")

        result = await servicer._verify_risk_approval("approval-123")

        assert result is False
