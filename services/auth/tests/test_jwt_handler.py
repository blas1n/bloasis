"""
Unit tests for JWT Handler (RS256 only).

Tests JWT token creation, validation, and claim extraction using RS256.
RSA test key fixtures are provided via conftest.py.
"""

import time
from pathlib import Path

import pytest

from src.jwt_handler import JWTHandler

# =============================================================================
# RS256 Initialization Tests
# =============================================================================

class TestJWTHandlerInitRS256:
    """Tests for JWTHandler initialization with RS256 algorithm."""

    def test_init_with_both_keys(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should initialize with both private and public keys."""
        private_path, public_path = rsa_key_paths
        handler = JWTHandler(
            private_key_path=private_path,
            public_key_path=public_path,
        )
        assert handler.algorithm == "RS256"
        assert handler.can_sign() is True
        assert handler.can_verify() is True

    def test_init_with_private_key_only(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should initialize with only private key (for signing)."""
        private_path, _ = rsa_key_paths
        handler = JWTHandler(private_key_path=private_path)
        assert handler.can_sign() is True
        assert handler.can_verify() is False

    def test_init_with_public_key_only(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should initialize with only public key (for verification)."""
        _, public_path = rsa_key_paths
        handler = JWTHandler(public_key_path=public_path)
        assert handler.can_sign() is False
        assert handler.can_verify() is True

    def test_init_without_keys_raises_error(self) -> None:
        """Should raise ValueError when no keys provided."""
        with pytest.raises(ValueError, match="requires private_key_path and/or public_key_path"):
            JWTHandler()

    def test_init_with_nonexistent_private_key_raises_error(self) -> None:
        """Should raise FileNotFoundError for nonexistent private key."""
        with pytest.raises(FileNotFoundError, match="Key file not found"):
            JWTHandler(private_key_path="/nonexistent/path/private.pem")

    def test_init_with_nonexistent_public_key_raises_error(self) -> None:
        """Should raise FileNotFoundError for nonexistent public key."""
        with pytest.raises(FileNotFoundError, match="Key file not found"):
            JWTHandler(public_key_path="/nonexistent/path/public.pem")

    def test_init_with_empty_key_file_raises_error(self, temp_key_dir: Path) -> None:
        """Should raise ValueError for empty key file."""
        empty_key_path = temp_key_dir / "empty.pem"
        empty_key_path.write_text("")
        with pytest.raises(ValueError, match="Key file is empty"):
            JWTHandler(private_key_path=str(empty_key_path))

    def test_get_public_key_returns_key_content(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should return public key content."""
        private_path, public_path = rsa_key_paths
        handler = JWTHandler(
            private_key_path=private_path,
            public_key_path=public_path,
        )
        public_key = handler.get_public_key()
        assert public_key is not None
        assert "BEGIN PUBLIC KEY" in public_key

    def test_get_public_key_returns_none_without_public_key(
        self, rsa_key_paths: tuple[str, str]
    ) -> None:
        """Should return None when initialized without public key."""
        private_path, _ = rsa_key_paths
        handler = JWTHandler(private_key_path=private_path)
        assert handler.get_public_key() is None


# =============================================================================
# Access Token Tests
# =============================================================================

class TestAccessToken:
    """Tests for access token creation and validation."""

    def test_create_access_token(self, jwt_handler: JWTHandler) -> None:
        """Should create valid access token."""
        token = jwt_handler.create_access_token(user_id="user-123")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_additional_claims(
        self, jwt_handler: JWTHandler
    ) -> None:
        """Should create access token with additional claims."""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            additional_claims={"role": "admin", "scope": ["read", "write"]},
        )
        claims = jwt_handler.validate_token(token)
        assert claims is not None
        assert claims["role"] == "admin"
        assert claims["scope"] == ["read", "write"]

    def test_validate_access_token(self, jwt_handler: JWTHandler) -> None:
        """Should validate and return claims from access token."""
        token = jwt_handler.create_access_token(user_id="user-123")
        claims = jwt_handler.validate_token(token)

        assert claims is not None
        assert claims["sub"] == "user-123"
        assert claims["type"] == "access"
        assert "exp" in claims
        assert "iat" in claims

    def test_get_user_id_from_access_token(self, jwt_handler: JWTHandler) -> None:
        """Should extract user_id from access token."""
        token = jwt_handler.create_access_token(user_id="user-456")
        assert jwt_handler.get_user_id(token) == "user-456"

    def test_get_token_type_for_access_token(self, jwt_handler: JWTHandler) -> None:
        """Should return 'access' for access token type."""
        token = jwt_handler.create_access_token(user_id="user-123")
        assert jwt_handler.get_token_type(token) == "access"


# =============================================================================
# Refresh Token Tests
# =============================================================================

class TestRefreshToken:
    """Tests for refresh token creation and validation."""

    def test_create_refresh_token(self, jwt_handler: JWTHandler) -> None:
        """Should create valid refresh token."""
        token = jwt_handler.create_refresh_token(user_id="user-123")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_validate_refresh_token(self, jwt_handler: JWTHandler) -> None:
        """Should validate and return claims from refresh token."""
        token = jwt_handler.create_refresh_token(user_id="user-123")
        claims = jwt_handler.validate_token(token)

        assert claims is not None
        assert claims["sub"] == "user-123"
        assert claims["type"] == "refresh"
        assert "exp" in claims
        assert "iat" in claims

    def test_get_user_id_from_refresh_token(self, jwt_handler: JWTHandler) -> None:
        """Should extract user_id from refresh token."""
        token = jwt_handler.create_refresh_token(user_id="user-789")
        assert jwt_handler.get_user_id(token) == "user-789"

    def test_get_token_type_for_refresh_token(self, jwt_handler: JWTHandler) -> None:
        """Should return 'refresh' for refresh token type."""
        token = jwt_handler.create_refresh_token(user_id="user-123")
        assert jwt_handler.get_token_type(token) == "refresh"


# =============================================================================
# Token Validation Tests
# =============================================================================

class TestTokenValidation:
    """Tests for token validation edge cases."""

    def test_validate_invalid_token(self, jwt_handler: JWTHandler) -> None:
        """Should return None for invalid token."""
        assert jwt_handler.validate_token("invalid-token") is None

    def test_validate_empty_token(self, jwt_handler: JWTHandler) -> None:
        """Should return None for empty token."""
        assert jwt_handler.validate_token("") is None

    def test_validate_malformed_token(self, jwt_handler: JWTHandler) -> None:
        """Should return None for malformed token."""
        assert jwt_handler.validate_token("part1.part2") is None

    def test_get_user_id_from_invalid_token(self, jwt_handler: JWTHandler) -> None:
        """Should return None for invalid token."""
        assert jwt_handler.get_user_id("invalid-token") is None

    def test_get_token_type_from_invalid_token(self, jwt_handler: JWTHandler) -> None:
        """Should return None for invalid token."""
        assert jwt_handler.get_token_type("invalid-token") is None

    def test_cannot_sign_without_private_key(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should raise error when trying to sign without private key."""
        _, public_path = rsa_key_paths
        handler = JWTHandler(public_key_path=public_path)
        with pytest.raises(ValueError, match="Signing key not available"):
            handler.create_access_token(user_id="user-123")

    def test_cannot_verify_without_public_key(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should return None when verifying without public key."""
        private_path, _ = rsa_key_paths
        handler = JWTHandler(private_key_path=private_path)
        token = handler.create_access_token(user_id="user-123")
        assert handler.validate_token(token) is None


# =============================================================================
# Token Expiry Tests
# =============================================================================

class TestExpiredToken:
    """Tests for expired token handling."""

    def test_validate_expired_token(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should return None for expired token."""
        private_path, public_path = rsa_key_paths
        handler = JWTHandler(
            private_key_path=private_path,
            public_key_path=public_path,
            access_token_expire_minutes=0,
        )
        token = handler.create_access_token(user_id="user-123")
        time.sleep(0.1)
        assert handler.validate_token(token) is None


class TestTokenExpiry:
    """Tests for token expiry time calculations."""

    def test_access_token_expire_seconds(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should return correct access token expiry in seconds."""
        private_path, _ = rsa_key_paths
        handler = JWTHandler(
            private_key_path=private_path,
            access_token_expire_minutes=15,
        )
        assert handler.get_access_token_expire_seconds() == 15 * 60

    def test_refresh_token_expire_seconds(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should return correct refresh token expiry in seconds."""
        private_path, _ = rsa_key_paths
        handler = JWTHandler(
            private_key_path=private_path,
            refresh_token_expire_days=7,
        )
        assert handler.get_refresh_token_expire_seconds() == 7 * 24 * 60 * 60

    def test_custom_expiry_values(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should handle custom expiry values."""
        private_path, _ = rsa_key_paths
        handler = JWTHandler(
            private_key_path=private_path,
            access_token_expire_minutes=60,
            refresh_token_expire_days=30,
        )
        assert handler.get_access_token_expire_seconds() == 60 * 60
        assert handler.get_refresh_token_expire_seconds() == 30 * 24 * 60 * 60
