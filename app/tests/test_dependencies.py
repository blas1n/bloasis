"""Tests for FastAPI dependency injection — auth and user access."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.dependencies import get_current_user, verify_user_access


class TestGetCurrentUser:
    async def test_valid_bearer_token(self):
        request = MagicMock()
        request.headers.get.return_value = "Bearer valid-token"

        mock_user_svc = MagicMock()
        mock_user_svc.validate_token.return_value = "user-1"

        result = await get_current_user(request, mock_user_svc)

        assert result == "user-1"

    async def test_missing_auth_header(self):
        request = MagicMock()
        request.headers.get.return_value = ""
        mock_user_svc = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, mock_user_svc)
        assert exc_info.value.status_code == 401
        assert "Missing authorization token" in exc_info.value.detail

    async def test_non_bearer_format(self):
        request = MagicMock()
        request.headers.get.return_value = "Token abc123"
        mock_user_svc = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, mock_user_svc)
        assert exc_info.value.status_code == 401

    async def test_invalid_token(self):
        request = MagicMock()
        request.headers.get.return_value = "Bearer invalid-token"

        mock_user_svc = MagicMock()
        mock_user_svc.validate_token.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, mock_user_svc)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail


class TestVerifyUserAccess:
    def test_matching_user_passes(self):
        result = verify_user_access("user-1", "user-1")
        assert result == "user-1"

    def test_mismatched_user_denied(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_user_access("user-1", "user-2")
        assert exc_info.value.status_code == 403
        assert "Access denied" in exc_info.value.detail
