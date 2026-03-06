"""Tests for signals router — /v1/users/{userId}/signals."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.models import AnalysisResult, MarketRegime, UserPreferences
from app.dependencies import get_current_user, get_strategy_service, get_user_service
from app.main import create_app

USER_ID = "test-user-id"


@pytest.fixture
def mock_strategy_svc():
    svc = AsyncMock()
    return svc


@pytest.fixture
def mock_user_svc():
    svc = AsyncMock()
    return svc


@pytest.fixture
def app(mock_strategy_svc, mock_user_svc):
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: USER_ID
    application.dependency_overrides[get_strategy_service] = lambda: mock_strategy_svc
    application.dependency_overrides[get_user_service] = lambda: mock_user_svc
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _make_analysis_result() -> AnalysisResult:
    return AnalysisResult(
        user_id=USER_ID,
        regime=MarketRegime(
            regime="bull",
            confidence=0.8,
            timestamp="2025-01-01T00:00:00Z",
        ),
        selected_sectors=["Technology"],
        stock_picks=[],
        signals=[],
    )


class TestGetSignals:
    def test_success(self, client, mock_strategy_svc, mock_user_svc):
        mock_user_svc.get_preferences.return_value = UserPreferences(
            user_id=USER_ID,
            risk_profile="moderate",
            preferred_sectors=["Technology"],
            excluded_sectors=["Energy"],
        )
        mock_strategy_svc.run_analysis.return_value = _make_analysis_result()

        resp = client.get(f"/v1/users/{USER_ID}/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["userId"] == USER_ID
        assert data["regime"]["regime"] == "bull"
        mock_strategy_svc.run_analysis.assert_awaited_once()

    def test_access_denied(self, client):
        resp = client.get("/v1/users/other-user-id/signals")
        assert resp.status_code == 403


class TestTriggerAnalysis:
    def test_success(self, client, mock_strategy_svc, mock_user_svc):
        mock_user_svc.get_preferences.return_value = UserPreferences(
            user_id=USER_ID,
            risk_profile="aggressive",
        )
        mock_strategy_svc.invalidate_user_cache = AsyncMock()
        mock_strategy_svc.run_analysis.return_value = _make_analysis_result()

        resp = client.post(f"/v1/users/{USER_ID}/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["userId"] == USER_ID
        mock_strategy_svc.invalidate_user_cache.assert_awaited_once_with(USER_ID)
        mock_strategy_svc.run_analysis.assert_awaited_once()

    def test_access_denied(self, client):
        resp = client.post("/v1/users/other-user-id/signals")
        assert resp.status_code == 403
