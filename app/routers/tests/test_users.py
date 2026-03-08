"""Tests for users router — /v1/users/{userId}/*."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.models import RiskProfile, UserPreferences
from app.dependencies import (
    get_broker_adapter,
    get_current_user,
    get_portfolio_service,
    get_user_service,
)
from app.main import create_app

USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"
USER_UUID = uuid.UUID(USER_ID)


@pytest.fixture
def mock_user_svc():
    svc = AsyncMock()
    return svc


@pytest.fixture
def mock_broker():
    return AsyncMock()


@pytest.fixture
def mock_portfolio_svc():
    return AsyncMock()


@pytest.fixture
def app(mock_user_svc, mock_broker, mock_portfolio_svc):
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: USER_UUID
    application.dependency_overrides[get_user_service] = lambda: mock_user_svc
    application.dependency_overrides[get_broker_adapter] = lambda: mock_broker
    application.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_svc
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestGetPreferences:
    def test_success(self, client, mock_user_svc):
        mock_user_svc.get_preferences.return_value = UserPreferences(
            user_id=USER_ID,
            risk_profile=RiskProfile.AGGRESSIVE,
            preferred_sectors=["Technology", "Healthcare"],
            excluded_sectors=["Energy"],
        )
        resp = client.get(f"/v1/users/{USER_ID}/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert data["userId"] == USER_ID
        assert data["riskProfile"] == "aggressive"
        assert "Technology" in data["preferredSectors"]
        assert "Energy" in data["excludedSectors"]

    def test_access_denied(self, client):
        resp = client.get(f"/v1/users/{OTHER_USER_ID}/preferences")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"


class TestUpdatePreferences:
    def test_success(self, client, mock_user_svc):
        mock_user_svc.update_preferences.return_value = UserPreferences(
            user_id=USER_ID,
            risk_profile=RiskProfile.CONSERVATIVE,
            preferred_sectors=["Healthcare"],
        )
        resp = client.put(
            f"/v1/users/{USER_ID}/preferences",
            json={
                "riskProfile": "conservative",
                "maxPortfolioRisk": "0.15",
                "maxPositionSize": "0.05",
                "preferredSectors": ["Healthcare"],
                "excludedSectors": [],
                "enableNotifications": True,
                "tradingEnabled": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["riskProfile"] == "conservative"
        mock_user_svc.update_preferences.assert_awaited_once()

    def test_access_denied(self, client):
        resp = client.put(
            f"/v1/users/{OTHER_USER_ID}/preferences",
            json={"riskProfile": "moderate"},
        )
        assert resp.status_code == 403


class TestGetBrokerStatus:
    def test_success(self, client, mock_user_svc):
        mock_user_svc.get_broker_status.return_value = {
            "configured": True,
            "connected": True,
            "equity": 0,
            "cash": 0,
            "errorMessage": "",
        }
        resp = client.get(f"/v1/users/{USER_ID}/broker")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["connected"] is True

    def test_access_denied(self, client):
        resp = client.get(f"/v1/users/{OTHER_USER_ID}/broker")
        assert resp.status_code == 403


class TestUpdateBrokerConfig:
    def test_success(self, client, mock_user_svc, mock_portfolio_svc):
        mock_user_svc.update_broker_config.return_value = {
            "configured": True,
            "connected": True,
            "positionsSynced": 3,
        }
        resp = client.put(
            f"/v1/users/{USER_ID}/broker",
            json={
                "apiKey": "PKTEST123",
                "secretKey": "secret456",
                "paper": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["positionsSynced"] == 3
        mock_user_svc.update_broker_config.assert_awaited_once_with(
            USER_UUID, "PKTEST123", "secret456", True, portfolio_svc=mock_portfolio_svc
        )

    def test_access_denied(self, client):
        resp = client.put(
            f"/v1/users/{OTHER_USER_ID}/broker",
            json={"apiKey": "x", "secretKey": "y", "paper": True},
        )
        assert resp.status_code == 403
