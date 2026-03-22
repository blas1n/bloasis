"""Tests for auth router — /v1/auth/tokens (Supabase Auth proxy)."""

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_user_service
from app.main import create_app

USER_ID = "00000000-0000-0000-0000-000000000001"
USER_UUID = uuid.UUID(USER_ID)


@pytest.fixture
def mock_user_svc() -> AsyncMock:
    svc = AsyncMock()
    return svc


@pytest.fixture
def app(mock_user_svc: AsyncMock) -> Any:
    application = create_app()
    application.dependency_overrides[get_user_service] = lambda: mock_user_svc
    application.dependency_overrides[get_current_user] = lambda: USER_UUID
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: Any) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestLogin:
    def test_login_success(self, client: TestClient, mock_user_svc: AsyncMock) -> None:
        mock_user_svc.login.return_value = {
            "accessToken": "access-tok",
            "refreshToken": "refresh-tok",
            "userId": USER_ID,
            "name": "Test User",
        }
        resp = client.post("/v1/auth/tokens", json={"email": "a@b.com", "password": "pw"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["accessToken"] == "access-tok"
        assert data["refreshToken"] == "refresh-tok"
        assert data["userId"] == USER_ID
        mock_user_svc.login.assert_awaited_once_with("a@b.com", "pw")

    def test_login_invalid_credentials(
        self, client: TestClient, mock_user_svc: AsyncMock
    ) -> None:
        mock_user_svc.login.return_value = None
        resp = client.post("/v1/auth/tokens", json={"email": "a@b.com", "password": "wrong"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    def test_login_missing_fields(self, client: TestClient) -> None:
        resp = client.post("/v1/auth/tokens", json={})
        assert resp.status_code == 422

    def test_login_missing_password(self, client: TestClient) -> None:
        resp = client.post("/v1/auth/tokens", json={"email": "a@b.com"})
        assert resp.status_code == 422


class TestSignup:
    def test_signup_success(self, client: TestClient, mock_user_svc: AsyncMock) -> None:
        mock_user_svc.signup.return_value = {
            "accessToken": "access-tok",
            "refreshToken": "refresh-tok",
            "userId": USER_ID,
            "name": "",
        }
        resp = client.post(
            "/v1/auth/tokens/signup", json={"email": "new@b.com", "password": "pw"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accessToken"] == "access-tok"
        mock_user_svc.signup.assert_awaited_once_with("new@b.com", "pw")

    def test_signup_failure(self, client: TestClient, mock_user_svc: AsyncMock) -> None:
        mock_user_svc.signup.return_value = None
        resp = client.post(
            "/v1/auth/tokens/signup", json={"email": "bad@b.com", "password": "pw"}
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Signup failed"


class TestMe:
    def test_success(self, client: TestClient, mock_user_svc: AsyncMock) -> None:
        mock_user_svc.get_user_info.return_value = {
            "userId": USER_ID,
            "name": "Test User",
            "email": "test@example.com",
        }
        resp = client.get("/v1/auth/me", headers={"Authorization": "Bearer some-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["userId"] == USER_ID
        mock_user_svc.get_user_info.assert_awaited_once_with("some-token")

    def test_missing_auth(self, client: TestClient) -> None:
        # me endpoint checks Authorization header directly
        app = client.app
        app.dependency_overrides.pop(get_current_user, None)  # type: ignore[union-attr]
        resp = client.get("/v1/auth/me")
        assert resp.status_code == 401


class TestRefresh:
    def test_refresh_success(self, client: TestClient, mock_user_svc: AsyncMock) -> None:
        mock_user_svc.refresh_token.return_value = {
            "accessToken": "new-access-tok",
            "refreshToken": "new-refresh-tok",
        }
        resp = client.post("/v1/auth/tokens/refresh", json={"refreshToken": "valid-refresh"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["accessToken"] == "new-access-tok"
        assert data["refreshToken"] == "new-refresh-tok"
        mock_user_svc.refresh_token.assert_awaited_once_with("valid-refresh")

    def test_refresh_invalid_token(self, client: TestClient, mock_user_svc: AsyncMock) -> None:
        mock_user_svc.refresh_token.return_value = None
        resp = client.post("/v1/auth/tokens/refresh", json={"refreshToken": "invalid"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid refresh token"


class TestLogout:
    def test_logout_success(self, client: TestClient, mock_user_svc: AsyncMock) -> None:
        mock_user_svc.logout.return_value = None
        resp = client.request(
            "DELETE",
            "/v1/auth/tokens",
            headers={"Authorization": "Bearer some-access-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_user_svc.logout.assert_awaited_once_with("some-access-token")

    def test_logout_no_token(self, client: TestClient, mock_user_svc: AsyncMock) -> None:
        resp = client.request("DELETE", "/v1/auth/tokens")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_user_svc.logout.assert_not_awaited()
