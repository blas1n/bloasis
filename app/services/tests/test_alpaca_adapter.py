"""Tests for AlpacaAdapter — httpx-mocked unit tests."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.models import OrderStatus
from app.services.brokers.alpaca import AlpacaAdapter


@pytest.fixture
def adapter():
    return AlpacaAdapter(
        api_key="test-key",
        secret_key="test-secret",
        base_url="https://paper-api.alpaca.markets",
    )


def _mock_response(status_code: int = 200, json_data: dict | list | None = None) -> httpx.Response:
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://test"),
    )
    return resp


class TestGetAccount:
    async def test_success(self, adapter):
        resp = _mock_response(
            200,
            {
                "equity": "100000.00",
                "cash": "50000.00",
                "buying_power": "50000.00",
            },
        )
        mock_client = AsyncMock()
        mock_client.get.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            account = await adapter.get_account()

        assert account.equity == Decimal("100000.00")
        assert account.cash == Decimal("50000.00")
        assert account.buying_power == Decimal("50000.00")


class TestGetPositions:
    async def test_success(self, adapter):
        resp = _mock_response(
            200,
            [
                {
                    "symbol": "AAPL",
                    "qty": "10",
                    "avg_entry_price": "150.00",
                    "current_price": "155.00",
                    "market_value": "1550.00",
                },
                {
                    "symbol": "TSLA",
                    "qty": "5",
                    "avg_entry_price": "200.00",
                    "current_price": "210.00",
                    "market_value": "1050.00",
                },
            ],
        )
        mock_client = AsyncMock()
        mock_client.get.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            positions = await adapter.get_positions()

        assert len(positions) == 2
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == Decimal("10")
        assert positions[1].symbol == "TSLA"

    async def test_empty_positions(self, adapter):
        resp = _mock_response(200, [])
        mock_client = AsyncMock()
        mock_client.get.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            positions = await adapter.get_positions()

        assert positions == []


class TestSubmitOrder:
    async def test_success(self, adapter):
        resp = _mock_response(
            200,
            {
                "id": "order-123",
                "client_order_id": "client-456",
                "symbol": "AAPL",
                "side": "buy",
                "qty": "10",
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": "150.50",
                "submitted_at": "2024-01-01T00:00:00Z",
            },
        )
        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.submit_order(
                symbol="AAPL",
                side="buy",
                qty=Decimal("10"),
                price=Decimal("150"),
                order_type="market",
                client_order_id="client-456",
            )

        assert result.order_id == "order-123"
        assert result.status == OrderStatus.FILLED
        assert result.filled_qty == Decimal("10")
        assert result.filled_avg_price == Decimal("150.50")

    async def test_rejected(self, adapter):
        resp = _mock_response(403, {"message": "Insufficient buying power"})
        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.submit_order(
                symbol="AAPL",
                side="buy",
                qty=Decimal("10"),
                price=Decimal("150"),
                order_type="market",
                client_order_id="client-456",
            )

        assert result.status == OrderStatus.FAILED
        assert "Alpaca error" in (result.error_message or "")


class TestGetOrderStatus:
    async def test_success(self, adapter):
        resp = _mock_response(
            200,
            {
                "id": "order-123",
                "client_order_id": "client-456",
                "symbol": "AAPL",
                "side": "buy",
                "qty": "10",
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": "150.50",
                "submitted_at": "2024-01-01T00:00:00Z",
                "filled_at": "2024-01-01T00:01:00Z",
            },
        )
        mock_client = AsyncMock()
        mock_client.get.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.get_order_status("order-123")

        assert result.status == OrderStatus.FILLED
        assert result.filled_at == "2024-01-01T00:01:00Z"


class TestCancelOrder:
    async def test_success(self, adapter):
        resp = _mock_response(204)
        mock_client = AsyncMock()
        mock_client.delete.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.cancel_order("order-123")

        assert result is True

    async def test_already_resolved_404(self, adapter):
        resp = _mock_response(404)
        mock_client = AsyncMock()
        mock_client.delete.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.cancel_order("order-123")

        assert result is True

    async def test_server_error(self, adapter):
        resp = _mock_response(500)
        mock_client = AsyncMock()
        mock_client.delete.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.cancel_order("order-123")

        assert result is False

    async def test_http_error(self, adapter):
        mock_client = AsyncMock()
        mock_client.delete.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.cancel_order("order-123")

        assert result is False


class TestTestConnection:
    async def test_success(self, adapter):
        resp = _mock_response(200, {"status": "ACTIVE"})
        mock_client = AsyncMock()
        mock_client.get.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.test_connection()

        assert result is True

    async def test_failure(self, adapter):
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.brokers.alpaca.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.test_connection()

        assert result is False


class TestNormalizeStatus:
    """Verify Alpaca raw status strings map to OrderStatus enum values."""

    @pytest.mark.parametrize(
        ("alpaca_status", "expected"),
        [
            ("new", OrderStatus.SUBMITTED),
            ("accepted", OrderStatus.SUBMITTED),
            ("pending_new", OrderStatus.SUBMITTED),
            ("partially_filled", OrderStatus.PARTIALLY_FILLED),
            ("filled", OrderStatus.FILLED),
            ("canceled", OrderStatus.CANCELLED),
            ("expired", OrderStatus.CANCELLED),
            ("rejected", OrderStatus.FAILED),
            ("unknown_future_status", OrderStatus.SUBMITTED),
        ],
    )
    def test_status_mapping(self, alpaca_status: str, expected: str) -> None:
        assert AlpacaAdapter._normalize_status(alpaca_status) == expected
