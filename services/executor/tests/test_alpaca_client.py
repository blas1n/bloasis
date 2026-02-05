"""Tests for Alpaca Client."""

import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.alpaca_client import AlpacaClient
from src.models import OrderStatus


@pytest.fixture
def mock_alpaca_module():
    """Mock the alpaca trading module."""
    # Create mock enums
    mock_order_side = MagicMock()
    mock_order_side.BUY = "buy"
    mock_order_side.SELL = "sell"

    mock_time_in_force = MagicMock()
    mock_time_in_force.DAY = "day"

    # Create mock request classes
    mock_market_request = MagicMock()
    mock_limit_request = MagicMock()
    mock_stop_loss_request = MagicMock()
    mock_take_profit_request = MagicMock()

    # Create mock trading client class
    mock_trading_client = MagicMock()

    # Create module structure
    mock_enums = MagicMock()
    mock_enums.OrderSide = mock_order_side
    mock_enums.TimeInForce = mock_time_in_force

    mock_requests = MagicMock()
    mock_requests.MarketOrderRequest = mock_market_request
    mock_requests.LimitOrderRequest = mock_limit_request
    mock_requests.StopLossRequest = mock_stop_loss_request
    mock_requests.TakeProfitRequest = mock_take_profit_request

    mock_client_module = MagicMock()
    mock_client_module.TradingClient = mock_trading_client

    mock_trading = MagicMock()
    mock_trading.enums = mock_enums
    mock_trading.requests = mock_requests
    mock_trading.client = mock_client_module

    mock_alpaca = MagicMock()
    mock_alpaca.trading = mock_trading

    # Patch sys.modules
    with patch.dict(
        sys.modules,
        {
            "alpaca": mock_alpaca,
            "alpaca.trading": mock_trading,
            "alpaca.trading.enums": mock_enums,
            "alpaca.trading.requests": mock_requests,
            "alpaca.trading.client": mock_client_module,
        },
    ):
        yield {
            "trading_client": mock_trading_client,
            "order_side": mock_order_side,
            "time_in_force": mock_time_in_force,
            "market_request": mock_market_request,
            "limit_request": mock_limit_request,
            "stop_loss_request": mock_stop_loss_request,
            "take_profit_request": mock_take_profit_request,
        }


class TestAlpacaClientInit:
    """Tests for AlpacaClient initialization."""

    def test_init_paper_trading(self):
        """Test initialization with paper trading."""
        client = AlpacaClient(
            api_key="test-key",
            secret_key="test-secret",
            paper=True,
        )

        assert client.api_key == "test-key"
        assert client.secret_key == "test-secret"
        assert client.paper is True
        assert client._client is None

    def test_init_live_trading_raises(self):
        """Test that live trading raises error."""
        with pytest.raises(ValueError, match="Live trading is not supported"):
            AlpacaClient(
                api_key="test-key",
                secret_key="test-secret",
                paper=False,
            )

    def test_init_default_config(self):
        """Test initialization with default config."""
        with patch("src.alpaca_client.config") as mock_config:
            mock_config.alpaca_api_key = "config-key"
            mock_config.alpaca_secret_key = "config-secret"

            client = AlpacaClient()

            assert client.api_key == "config-key"
            assert client.secret_key == "config-secret"


class TestAlpacaClientGetClient:
    """Tests for _get_client method."""

    def test_get_client_creates_client(self, mock_alpaca_module):
        """Test that _get_client creates a client."""
        client = AlpacaClient(
            api_key="test-key",
            secret_key="test-secret",
        )

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading_client.return_value = MagicMock()

        result = client._get_client()

        mock_trading_client.assert_called_once_with(
            api_key="test-key",
            secret_key="test-secret",
            paper=True,
        )
        assert result is not None

    def test_get_client_reuses_client(self, mock_alpaca_module):
        """Test that _get_client reuses existing client."""
        client = AlpacaClient(
            api_key="test-key",
            secret_key="test-secret",
        )

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_instance = MagicMock()
        mock_trading_client.return_value = mock_instance

        first = client._get_client()
        second = client._get_client()

        assert first is second
        mock_trading_client.assert_called_once()

    def test_get_client_no_api_key_raises(self):
        """Test that missing API key raises error."""
        with patch("src.alpaca_client.config") as mock_config:
            mock_config.alpaca_api_key = None
            mock_config.alpaca_secret_key = "secret"

            client = AlpacaClient()

            with pytest.raises(ValueError, match="API keys not configured"):
                client._get_client()

    def test_get_client_no_secret_key_raises(self):
        """Test that missing secret key raises error."""
        with patch("src.alpaca_client.config") as mock_config:
            mock_config.alpaca_api_key = "key"
            mock_config.alpaca_secret_key = None

            client = AlpacaClient()

            with pytest.raises(ValueError, match="API keys not configured"):
                client._get_client()


class TestAlpacaClientMarketOrder:
    """Tests for market order submission."""

    @pytest.mark.asyncio
    async def test_submit_market_order_buy_success(self, mock_alpaca_module):
        """Test successful buy market order."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.client_order_id = "client-123"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "10"
        mock_order.status.value = "new"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.submit_order.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.submit_market_order(
            symbol="AAPL",
            qty=Decimal("10"),
            side="buy",
            client_order_id="client-123",
        )

        assert result.order_id == "order-123"
        assert result.symbol == "AAPL"
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_submit_market_order_sell_success(self, mock_alpaca_module):
        """Test successful sell market order."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-124"
        mock_order.client_order_id = "client-124"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "sell"
        mock_order.qty = "5"
        mock_order.status.value = "new"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.submit_order.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.submit_market_order(
            symbol="AAPL",
            qty=Decimal("5"),
            side="sell",
        )

        assert result.order_id == "order-124"
        assert result.side == "sell"

    @pytest.mark.asyncio
    async def test_submit_market_order_failure(self, mock_alpaca_module):
        """Test market order submission failure."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.submit_order.side_effect = Exception("API error")
        mock_trading_client.return_value = mock_trading

        result = await client.submit_market_order(
            symbol="INVALID",
            qty=Decimal("10"),
            side="buy",
            client_order_id="client-fail",
        )

        assert result.status == OrderStatus.REJECTED
        assert "API error" in result.error_message


class TestAlpacaClientLimitOrder:
    """Tests for limit order submission."""

    @pytest.mark.asyncio
    async def test_submit_limit_order_success(self, mock_alpaca_module):
        """Test successful limit order."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-125"
        mock_order.client_order_id = "client-125"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "10"
        mock_order.status.value = "new"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.submit_order.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.submit_limit_order(
            symbol="AAPL",
            qty=Decimal("10"),
            side="buy",
            limit_price=Decimal("175.00"),
            client_order_id="client-125",
        )

        assert result.order_id == "order-125"
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_submit_limit_order_failure(self, mock_alpaca_module):
        """Test limit order submission failure."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.submit_order.side_effect = Exception("Invalid price")
        mock_trading_client.return_value = mock_trading

        result = await client.submit_limit_order(
            symbol="AAPL",
            qty=Decimal("10"),
            side="buy",
            limit_price=Decimal("0.01"),
        )

        assert result.status == OrderStatus.REJECTED
        assert "Invalid price" in result.error_message


class TestAlpacaClientBracketOrder:
    """Tests for bracket order submission."""

    @pytest.mark.asyncio
    async def test_submit_bracket_order_success(self, mock_alpaca_module):
        """Test successful bracket order."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-126"
        mock_order.client_order_id = "client-126"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "10"
        mock_order.status.value = "new"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.submit_order.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.submit_bracket_order(
            symbol="AAPL",
            qty=Decimal("10"),
            side="buy",
            stop_loss=Decimal("170.00"),
            take_profit=Decimal("185.00"),
            client_order_id="client-126",
        )

        assert result.order_id == "order-126"
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_submit_bracket_order_failure(self, mock_alpaca_module):
        """Test bracket order submission failure."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.submit_order.side_effect = Exception("Invalid stop price")
        mock_trading_client.return_value = mock_trading

        result = await client.submit_bracket_order(
            symbol="AAPL",
            qty=Decimal("10"),
            side="buy",
            stop_loss=Decimal("200.00"),
            take_profit=Decimal("185.00"),
        )

        assert result.status == OrderStatus.REJECTED
        assert "Invalid stop price" in result.error_message


class TestAlpacaClientOrderStatus:
    """Tests for order status retrieval."""

    @pytest.mark.asyncio
    async def test_get_order_status_success(self, mock_alpaca_module):
        """Test successful order status retrieval."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.client_order_id = "client-123"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "10"
        mock_order.status.value = "filled"
        mock_order.filled_qty = "10"
        mock_order.filled_avg_price = "175.50"
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = "2025-01-29T10:00:01Z"

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.get_order_status("order-123")

        assert result.order_id == "order-123"
        assert result.status == OrderStatus.FILLED
        assert result.filled_qty == Decimal("10")

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, mock_alpaca_module):
        """Test order status for non-existent order."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.get_order_by_id.side_effect = Exception("Order not found")
        mock_trading_client.return_value = mock_trading

        with pytest.raises(Exception, match="Order not found"):
            await client.get_order_status("nonexistent")


class TestAlpacaClientCancelOrder:
    """Tests for order cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, mock_alpaca_module):
        """Test successful order cancellation."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading_client.return_value = mock_trading

        result = await client.cancel_order("order-123")

        assert result is True
        mock_trading.cancel_order_by_id.assert_called_once_with("order-123")

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, mock_alpaca_module):
        """Test failed order cancellation."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.cancel_order_by_id.side_effect = Exception("Cannot cancel")
        mock_trading_client.return_value = mock_trading

        result = await client.cancel_order("order-123")

        assert result is False


class TestAlpacaClientGetAccount:
    """Tests for account retrieval."""

    @pytest.mark.asyncio
    async def test_get_account_success(self, mock_alpaca_module):
        """Test successful account retrieval."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_account = MagicMock()
        mock_account.cash = "100000.00"
        mock_account.buying_power = "200000.00"
        mock_account.portfolio_value = "150000.00"
        mock_account.equity = "150000.00"

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.get_account.return_value = mock_account
        mock_trading_client.return_value = mock_trading

        result = await client.get_account()

        assert result.cash == Decimal("100000.00")
        assert result.buying_power == Decimal("200000.00")
        assert result.portfolio_value == Decimal("150000.00")


class TestAlpacaClientOrderResultMapping:
    """Tests for order result status mapping."""

    @pytest.mark.asyncio
    async def test_status_mapping_partially_filled(self, mock_alpaca_module):
        """Test partially filled status mapping."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-127"
        mock_order.client_order_id = "client-127"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "100"
        mock_order.status.value = "partially_filled"
        mock_order.filled_qty = "50"
        mock_order.filled_avg_price = "175.00"
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.get_order_status("order-127")

        assert result.status == OrderStatus.PARTIALLY_FILLED
        assert result.filled_qty == Decimal("50")

    @pytest.mark.asyncio
    async def test_status_mapping_cancelled(self, mock_alpaca_module):
        """Test cancelled status mapping."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-128"
        mock_order.client_order_id = "client-128"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "10"
        mock_order.status.value = "canceled"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.get_order_status("order-128")

        assert result.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_status_mapping_expired(self, mock_alpaca_module):
        """Test expired status mapping."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-129"
        mock_order.client_order_id = "client-129"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "10"
        mock_order.status.value = "expired"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.get_order_status("order-129")

        assert result.status == OrderStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_status_mapping_rejected(self, mock_alpaca_module):
        """Test rejected status mapping."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-130"
        mock_order.client_order_id = "client-130"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "10"
        mock_order.status.value = "rejected"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.get_order_status("order-130")

        assert result.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_status_mapping_unknown(self, mock_alpaca_module):
        """Test unknown status defaults to PENDING."""
        client = AlpacaClient(api_key="key", secret_key="secret")

        mock_order = MagicMock()
        mock_order.id = "order-131"
        mock_order.client_order_id = "client-131"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = "10"
        mock_order.status.value = "unknown_status"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_order.submitted_at = "2025-01-29T10:00:00Z"
        mock_order.filled_at = None

        mock_trading_client = mock_alpaca_module["trading_client"]
        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order
        mock_trading_client.return_value = mock_trading

        result = await client.get_order_status("order-131")

        assert result.status == OrderStatus.PENDING
