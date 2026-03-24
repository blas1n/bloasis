"""Tests for FastAPI dependency injection — auth and user access."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.dependencies import get_current_user, verify_user_access

USER_ID = "00000000-0000-0000-0000-000000000001"
USER_UUID = uuid.UUID(USER_ID)
OTHER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class TestGetCurrentUser:
    async def test_valid_bearer_token(self) -> None:
        request = MagicMock()
        request.headers.get.return_value = "Bearer valid-token"

        mock_jwks = MagicMock()
        mock_key = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = mock_key
        request.app.state.jwks_client = mock_jwks

        with patch("app.dependencies.jwt") as mock_jwt:
            mock_jwt.decode.return_value = {"sub": USER_ID, "aud": "authenticated"}
            mock_jwt.ExpiredSignatureError = Exception
            mock_jwt.InvalidTokenError = Exception
            result = await get_current_user(request)

        assert result == USER_UUID
        mock_jwks.get_signing_key_from_jwt.assert_called_once_with("valid-token")

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

    async def test_expired_token(self) -> None:
        import jwt as real_jwt

        request = MagicMock()
        request.headers.get.return_value = "Bearer expired-token"

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = MagicMock()
        request.app.state.jwks_client = mock_jwks

        with patch("app.dependencies.jwt") as mock_jwt:
            mock_jwt.ExpiredSignatureError = real_jwt.ExpiredSignatureError
            mock_jwt.InvalidTokenError = real_jwt.InvalidTokenError
            mock_jwt.decode.side_effect = real_jwt.ExpiredSignatureError()
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    async def test_invalid_token(self) -> None:
        import jwt as real_jwt

        request = MagicMock()
        request.headers.get.return_value = "Bearer invalid-token"

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.side_effect = real_jwt.InvalidTokenError()
        request.app.state.jwks_client = mock_jwks

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail

    async def test_invalid_uuid_in_token(self) -> None:
        request = MagicMock()
        request.headers.get.return_value = "Bearer valid-token"

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = MagicMock()
        request.app.state.jwks_client = mock_jwks

        with patch("app.dependencies.jwt") as mock_jwt:
            mock_jwt.decode.return_value = {"sub": "not-a-uuid"}
            mock_jwt.ExpiredSignatureError = Exception
            mock_jwt.InvalidTokenError = Exception
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)
        assert exc_info.value.status_code == 401


class TestVerifyUserAccess:
    def test_matching_user_passes(self) -> None:
        result = verify_user_access(USER_UUID, USER_UUID)
        assert result == USER_UUID

    def test_mismatched_user_denied(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            verify_user_access(USER_UUID, OTHER_UUID)
        assert exc_info.value.status_code == 403
        assert "Access denied" in exc_info.value.detail
