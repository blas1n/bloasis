"""Tests for FastAPI dependency injection — auth and user access."""

import uuid
from unittest.mock import MagicMock

import pytest
from bsvibe_auth import AuthError, BSVibeUser
from fastapi import HTTPException

from app.dependencies import get_current_user, verify_user_access

USER_ID = "00000000-0000-0000-0000-000000000001"
USER_UUID = uuid.UUID(USER_ID)
OTHER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _make_bsvibe_user(user_id: str = USER_ID) -> BSVibeUser:
    return BSVibeUser(id=user_id, email="test@example.com")


class TestGetCurrentUser:
    async def test_valid_bearer_token(self) -> None:
        request = MagicMock()
        request.headers.get.return_value = "Bearer valid-token"

        mock_provider = MagicMock()
        mock_provider.verify_token.return_value = _make_bsvibe_user()
        request.app.state.auth_provider = mock_provider

        result = await get_current_user(request)

        assert result == USER_UUID
        mock_provider.verify_token.assert_called_once_with("valid-token")

    async def test_missing_auth_header(self) -> None:
        request = MagicMock()
        request.headers.get.return_value = ""

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401
        assert "Missing authorization token" in exc_info.value.detail

    async def test_non_bearer_format(self) -> None:
        request = MagicMock()
        request.headers.get.return_value = "Token abc123"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    async def test_invalid_token(self) -> None:
        request = MagicMock()
        request.headers.get.return_value = "Bearer invalid-token"

        mock_provider = MagicMock()
        mock_provider.verify_token.side_effect = AuthError("Invalid token")
        request.app.state.auth_provider = mock_provider

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail

    async def test_invalid_uuid_in_token(self) -> None:
        request = MagicMock()
        request.headers.get.return_value = "Bearer valid-token"

        mock_provider = MagicMock()
        mock_provider.verify_token.return_value = _make_bsvibe_user("not-a-uuid")
        request.app.state.auth_provider = mock_provider

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail


class TestVerifyUserAccess:
    def test_matching_user_passes(self) -> None:
        result = verify_user_access(USER_UUID, USER_UUID)
        assert result == USER_UUID

    def test_mismatched_user_denied(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            verify_user_access(USER_UUID, OTHER_UUID)
        assert exc_info.value.status_code == 403
        assert "Access denied" in exc_info.value.detail
