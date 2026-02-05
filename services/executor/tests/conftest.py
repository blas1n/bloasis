"""Test fixtures for Executor Service."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import AccountInfo, OrderResult, OrderStatus


@pytest.fixture
def mock_alpaca_client():
    """Create mock Alpaca client."""
    client = AsyncMock()
    client.submit_market_order = AsyncMock(
        return_value=OrderResult(
            order_id="order-123",
            client_order_id="bloasis-abc12345",
            symbol="AAPL",
            side="buy",
            qty=Decimal("10"),
            status=OrderStatus.SUBMITTED,
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            submitted_at="2025-01-29T10:00:00Z",
            filled_at=None,
        )
    )
    client.submit_limit_order = AsyncMock(
        return_value=OrderResult(
            order_id="order-124",
            client_order_id="bloasis-def12345",
            symbol="AAPL",
            side="buy",
            qty=Decimal("10"),
            status=OrderStatus.SUBMITTED,
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            submitted_at="2025-01-29T10:00:00Z",
            filled_at=None,
        )
    )
    client.submit_bracket_order = AsyncMock(
        return_value=OrderResult(
            order_id="order-125",
            client_order_id="bloasis-ghi12345",
            symbol="AAPL",
            side="buy",
            qty=Decimal("10"),
            status=OrderStatus.SUBMITTED,
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            submitted_at="2025-01-29T10:00:00Z",
            filled_at=None,
        )
    )
    client.get_order_status = AsyncMock(
        return_value=OrderResult(
            order_id="order-123",
            client_order_id="bloasis-abc12345",
            symbol="AAPL",
            side="buy",
            qty=Decimal("10"),
            status=OrderStatus.FILLED,
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("175.50"),
            submitted_at="2025-01-29T10:00:00Z",
            filled_at="2025-01-29T10:00:01Z",
        )
    )
    client.cancel_order = AsyncMock(return_value=True)
    client.get_account = AsyncMock(
        return_value=AccountInfo(
            cash=Decimal("100000"),
            buying_power=Decimal("200000"),
            portfolio_value=Decimal("150000"),
            equity=Decimal("150000"),
        )
    )
    return client


@pytest.fixture
def mock_event_publisher():
    """Create mock event publisher."""
    publisher = AsyncMock()
    publisher.publish_order_executed = AsyncMock()
    publisher.publish_order_cancelled = AsyncMock()
    publisher.connect = AsyncMock()
    publisher.close = AsyncMock()
    return publisher


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    client = AsyncMock()
    client.exists = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.hset = AsyncMock(return_value=1)
    client.hgetall = AsyncMock(return_value={})
    client.expire = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.connect = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_grpc_context():
    """Create mock gRPC context."""
    context = MagicMock()
    context.abort = AsyncMock()
    return context


@pytest.fixture
def sample_order_result():
    """Create a sample order result."""
    return OrderResult(
        order_id="order-123",
        client_order_id="bloasis-abc12345",
        symbol="AAPL",
        side="buy",
        qty=Decimal("10"),
        status=OrderStatus.SUBMITTED,
        filled_qty=Decimal("0"),
        filled_avg_price=None,
        submitted_at="2025-01-29T10:00:00Z",
        filled_at=None,
    )


@pytest.fixture
def rejected_order_result():
    """Create a rejected order result."""
    return OrderResult(
        order_id="",
        client_order_id="bloasis-fail123",
        symbol="INVALID",
        side="buy",
        qty=Decimal("10"),
        status=OrderStatus.REJECTED,
        filled_qty=Decimal("0"),
        filled_avg_price=None,
        submitted_at="",
        filled_at=None,
        error_message="Invalid symbol",
    )
