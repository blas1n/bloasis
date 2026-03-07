"""Tests for trading router — /v1/users/{userId}/trading."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_executor_service
from app.main import create_app

USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"
USER_UUID = uuid.UUID(USER_ID)


@pytest.fixture
def mock_executor_svc():
    svc = AsyncMock()
    return svc


@pytest.fixture
def app(mock_executor_svc):
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: USER_UUID
    application.dependency_overrides[get_executor_service] = lambda: mock_executor_svc
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestGetTradingStatus:
    def test_success(self, client, mock_executor_svc):
        mock_executor_svc.get_trading_status.return_value = {
            "tradingEnabled": True,
            "status": "active",
            "lastChanged": "",
        }
        resp = client.get(f"/v1/users/{USER_ID}/trading")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tradingEnabled"] is True
        assert data["status"] == "active"

    def test_access_denied(self, client):
        resp = client.get(f"/v1/users/{OTHER_USER_ID}/trading")
        assert resp.status_code == 403


class TestStartTrading:
    def test_success(self, client, mock_executor_svc):
        mock_executor_svc.start_trading.return_value = {
            "tradingEnabled": True,
            "status": "active",
        }
        resp = client.post(f"/v1/users/{USER_ID}/trading")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tradingEnabled"] is True
        assert data["status"] == "active"
        mock_executor_svc.start_trading.assert_awaited_once_with(USER_UUID)

    def test_access_denied(self, client):
        resp = client.post(f"/v1/users/{OTHER_USER_ID}/trading")
        assert resp.status_code == 403


class TestStopTrading:
    def test_success_soft(self, client, mock_executor_svc):
        mock_executor_svc.stop_trading.return_value = {
            "tradingEnabled": False,
            "status": "soft_stopped",
        }
        resp = client.request(
            "DELETE",
            f"/v1/users/{USER_ID}/trading",
            json={"mode": "soft"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tradingEnabled"] is False
        mock_executor_svc.stop_trading.assert_awaited_once_with(USER_UUID, "soft")

    def test_success_hard(self, client, mock_executor_svc):
        mock_executor_svc.stop_trading.return_value = {
            "tradingEnabled": False,
            "status": "hard_stopped",
        }
        resp = client.request(
            "DELETE",
            f"/v1/users/{USER_ID}/trading",
            json={"mode": "hard"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "hard_stopped"

    def test_success_no_body(self, client, mock_executor_svc):
        """Without body, mode should default to 'soft'."""
        mock_executor_svc.stop_trading.return_value = {
            "tradingEnabled": False,
            "status": "soft_stopped",
        }
        resp = client.delete(f"/v1/users/{USER_ID}/trading")
        assert resp.status_code == 200
        mock_executor_svc.stop_trading.assert_awaited_once_with(USER_UUID, "soft")

    def test_access_denied(self, client):
        resp = client.delete(f"/v1/users/{OTHER_USER_ID}/trading")
        assert resp.status_code == 403
