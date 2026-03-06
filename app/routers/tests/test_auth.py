"""Tests for auth router — /v1/auth/tokens."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_user_service
from app.main import create_app


@pytest.fixture
def mock_user_svc():
    svc = AsyncMock()
    return svc


@pytest.fixture
def app(mock_user_svc):
    application = create_app()
    application.dependency_overrides[get_user_service] = lambda: mock_user_svc
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestLogin:
    def test_login_success(self, client, mock_user_svc):
        mock_user_svc.login.return_value = {
            "accessToken": "access-tok",
            "refreshToken": "refresh-tok",
            "userId": "user-1",
            "name": "Test User",
        }
        resp = client.post("/v1/auth/tokens", json={"email": "a@b.com", "password": "pw"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["accessToken"] == "access-tok"
        assert data["refreshToken"] == "refresh-tok"
        assert data["userId"] == "user-1"
        mock_user_svc.login.assert_awaited_once_with("a@b.com", "pw")

    def test_login_invalid_credentials(self, client, mock_user_svc):
        mock_user_svc.login.return_value = None
        resp = client.post("/v1/auth/tokens", json={"email": "a@b.com", "password": "wrong"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    def test_login_missing_fields(self, client):
        resp = client.post("/v1/auth/tokens", json={})
        assert resp.status_code == 422

    def test_login_missing_password(self, client):
        resp = client.post("/v1/auth/tokens", json={"email": "a@b.com"})
        assert resp.status_code == 422


class TestRefresh:
    def test_refresh_success(self, client, mock_user_svc):
        mock_user_svc.refresh_token.return_value = {"accessToken": "new-access-tok"}
        resp = client.post("/v1/auth/tokens/refresh", json={"refreshToken": "valid-refresh"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["accessToken"] == "new-access-tok"
        mock_user_svc.refresh_token.assert_awaited_once_with("valid-refresh")

    def test_refresh_invalid_token(self, client, mock_user_svc):
        mock_user_svc.refresh_token.return_value = None
        resp = client.post("/v1/auth/tokens/refresh", json={"refreshToken": "invalid"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid refresh token"


class TestLogout:
    def test_logout_success(self, client, mock_user_svc):
        mock_user_svc.logout.return_value = None
        resp = client.request("DELETE", "/v1/auth/tokens", json={"refreshToken": "some-token"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_user_svc.logout.assert_awaited_once_with("some-token")
