"""Tests for market router — /v1/market/regimes/current."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.models import MarketRegime
from app.dependencies import get_current_user, get_market_regime_service
from app.main import create_app


@pytest.fixture
def mock_regime_svc():
    svc = AsyncMock()
    return svc


@pytest.fixture
def app(mock_regime_svc):
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: "test-user-id"
    application.dependency_overrides[get_market_regime_service] = lambda: mock_regime_svc
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestGetCurrentRegime:
    def test_success(self, client, mock_regime_svc):
        mock_regime_svc.get_current.return_value = MarketRegime(
            regime="bull",
            confidence=0.85,
            timestamp="2025-01-01T00:00:00Z",
            trigger="baseline",
            reasoning="Markets are bullish",
            risk_level="low",
        )
        resp = client.get("/v1/market/regimes/current")
        assert resp.status_code == 200
        data = resp.json()
        # CamelJSONResponse converts snake_case keys to camelCase
        assert data["regime"] == "bull"
        assert data["confidence"] == 0.85
        assert data["riskLevel"] == "low"
        assert data["reasoning"] == "Markets are bullish"

    def test_requires_auth(self, mock_regime_svc):
        """Without auth override, request should be rejected with 401."""
        from fastapi import HTTPException

        def deny_auth():
            raise HTTPException(status_code=401, detail="Missing authorization token")

        application = create_app()
        application.dependency_overrides[get_current_user] = deny_auth
        application.dependency_overrides[get_market_regime_service] = lambda: mock_regime_svc
        c = TestClient(application, raise_server_exceptions=False)
        resp = c.get("/v1/market/regimes/current")
        assert resp.status_code == 401
        application.dependency_overrides.clear()
