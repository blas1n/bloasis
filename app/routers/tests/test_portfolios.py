"""Tests for portfolios router — /v1/portfolios/{userId}/*."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.models import Portfolio, Position, Trade
from app.dependencies import get_broker_adapter, get_current_user, get_portfolio_service
from app.main import create_app

USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def mock_portfolio_svc():
    svc = AsyncMock()
    return svc


@pytest.fixture
def mock_broker():
    return AsyncMock()


@pytest.fixture
def app(mock_portfolio_svc, mock_broker):
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: uuid.UUID(USER_ID)
    application.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_svc
    application.dependency_overrides[get_broker_adapter] = lambda: mock_broker
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _make_portfolio() -> Portfolio:
    return Portfolio(
        user_id=USER_ID,
        total_value=Decimal("50000"),
        cash_balance=Decimal("20000"),
        invested_value=Decimal("30000"),
        total_return=5.0,
        total_return_amount=Decimal("1500"),
        daily_pnl=Decimal("200"),
        daily_pnl_pct=Decimal("0.40"),
        positions=[
            Position(
                symbol="AAPL",
                quantity=10,
                avg_cost=Decimal("140"),
                current_price=Decimal("150"),
                current_value=Decimal("1500"),
                unrealized_pnl=Decimal("100"),
                sector="Technology",
            ),
        ],
    )


class TestGetPortfolio:
    def test_success(self, client, mock_portfolio_svc):
        mock_portfolio_svc.get_portfolio.return_value = _make_portfolio()
        resp = client.get(f"/v1/portfolios/{USER_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["userId"] == USER_ID
        assert data["totalEquity"] is not None
        assert data["buyingPower"] is not None
        assert data["marketValue"] is not None
        assert data["unrealizedPnl"] is not None
        assert data["positionCount"] == 1

    def test_access_denied_different_user(self, client):
        resp = client.get(f"/v1/portfolios/{OTHER_USER_ID}")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"


class TestGetPositions:
    def test_success(self, client, mock_portfolio_svc):
        mock_portfolio_svc.get_positions.return_value = [
            Position(
                symbol="AAPL",
                quantity=10,
                avg_cost=Decimal("140"),
                current_price=Decimal("150"),
                current_value=Decimal("1500"),
                unrealized_pnl=Decimal("100"),
            ),
            Position(
                symbol="TSLA",
                quantity=5,
                avg_cost=Decimal("200"),
                current_price=Decimal("220"),
                current_value=Decimal("1100"),
                unrealized_pnl=Decimal("100"),
            ),
        ]
        resp = client.get(f"/v1/portfolios/{USER_ID}/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["userId"] == USER_ID
        assert len(data["positions"]) == 2

    def test_access_denied(self, client):
        resp = client.get(f"/v1/portfolios/{OTHER_USER_ID}/positions")
        assert resp.status_code == 403


class TestGetTrades:
    def test_success(self, client, mock_portfolio_svc):
        mock_portfolio_svc.get_trades.return_value = [
            Trade(
                order_id="ord-1",
                symbol="AAPL",
                side="buy",
                qty=Decimal("10"),
                price=Decimal("150"),
                realized_pnl=Decimal("50"),
            ),
        ]
        resp = client.get(f"/v1/portfolios/{USER_ID}/trades")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["trades"]) == 1
        assert data["totalRealizedPnl"] is not None

    def test_access_denied(self, client):
        resp = client.get(f"/v1/portfolios/{OTHER_USER_ID}/trades")
        assert resp.status_code == 403


class TestSyncPortfolio:
    def test_success(self, client, mock_portfolio_svc):
        mock_portfolio_svc.sync_with_broker.return_value = {
            "success": True,
            "positionsSynced": 3,
        }
        resp = client.post(f"/v1/portfolios/{USER_ID}/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["positionsSynced"] == 3

    def test_access_denied(self, client):
        resp = client.post(f"/v1/portfolios/{OTHER_USER_ID}/sync")
        assert resp.status_code == 403
