"""
Unit tests for JWT Handler.

Tests JWT token creation, validation, and claim extraction.
"""

import time

import pytest

from src.jwt_handler import JWTHandler


class TestJWTHandlerInit:
    """Tests for JWTHandler initialization."""

    def test_init_with_valid_secret(self) -> None:
        """Should initialize with valid secret key."""
        handler = JWTHandler(secret_key="test-secret-key")
        assert handler.secret_key == "test-secret-key"
        assert handler.algorithm == "HS256"

    def test_init_with_custom_algorithm(self) -> None:
        """Should initialize with custom algorithm."""
        handler = JWTHandler(secret_key="test-secret-key", algorithm="HS384")
        assert handler.algorithm == "HS384"

    def test_init_with_custom_expiry(self) -> None:
        """Should initialize with custom expiry times."""
        handler = JWTHandler(
            secret_key="test-secret-key",
            access_token_expire_minutes=30,
            refresh_token_expire_days=14,
        )
        assert handler.get_access_token_expire_seconds() == 30 * 60
        assert handler.get_refresh_token_expire_seconds() == 14 * 24 * 60 * 60

    def test_init_with_empty_secret_raises_error(self) -> None:
        """Should raise ValueError for empty secret key."""
        with pytest.raises(ValueError, match="JWT secret key is required"):
            JWTHandler(secret_key="")


class TestAccessToken:
    """Tests for access token creation and validation."""

    @pytest.fixture
    def handler(self) -> JWTHandler:
        """Create a JWTHandler for testing."""
        return JWTHandler(
            secret_key="test-secret-key-for-testing",
            access_token_expire_minutes=15,
        )

    def test_create_access_token(self, handler: JWTHandler) -> None:
        """Should create valid access token."""
        token = handler.create_access_token(user_id="user-123")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_additional_claims(self, handler: JWTHandler) -> None:
        """Should create access token with additional claims."""
        token = handler.create_access_token(
            user_id="user-123",
            additional_claims={"role": "admin", "scope": ["read", "write"]},
        )
        claims = handler.validate_token(token)
        assert claims is not None
        assert claims["role"] == "admin"
        assert claims["scope"] == ["read", "write"]

    def test_validate_access_token(self, handler: JWTHandler) -> None:
        """Should validate and return claims from access token."""
        token = handler.create_access_token(user_id="user-123")
        claims = handler.validate_token(token)

        assert claims is not None
        assert claims["sub"] == "user-123"
        assert claims["type"] == "access"
        assert "exp" in claims
        assert "iat" in claims

    def test_get_user_id_from_access_token(self, handler: JWTHandler) -> None:
        """Should extract user_id from access token."""
        token = handler.create_access_token(user_id="user-456")
        user_id = handler.get_user_id(token)

        assert user_id == "user-456"

    def test_get_token_type_for_access_token(self, handler: JWTHandler) -> None:
        """Should return 'access' for access token type."""
        token = handler.create_access_token(user_id="user-123")
        token_type = handler.get_token_type(token)

        assert token_type == "access"


class TestRefreshToken:
    """Tests for refresh token creation and validation."""

    @pytest.fixture
    def handler(self) -> JWTHandler:
        """Create a JWTHandler for testing."""
        return JWTHandler(
            secret_key="test-secret-key-for-testing",
            refresh_token_expire_days=7,
        )

    def test_create_refresh_token(self, handler: JWTHandler) -> None:
        """Should create valid refresh token."""
        token = handler.create_refresh_token(user_id="user-123")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_validate_refresh_token(self, handler: JWTHandler) -> None:
        """Should validate and return claims from refresh token."""
        token = handler.create_refresh_token(user_id="user-123")
        claims = handler.validate_token(token)

        assert claims is not None
        assert claims["sub"] == "user-123"
        assert claims["type"] == "refresh"
        assert "exp" in claims
        assert "iat" in claims

    def test_get_user_id_from_refresh_token(self, handler: JWTHandler) -> None:
        """Should extract user_id from refresh token."""
        token = handler.create_refresh_token(user_id="user-789")
        user_id = handler.get_user_id(token)

        assert user_id == "user-789"

    def test_get_token_type_for_refresh_token(self, handler: JWTHandler) -> None:
        """Should return 'refresh' for refresh token type."""
        token = handler.create_refresh_token(user_id="user-123")
        token_type = handler.get_token_type(token)

        assert token_type == "refresh"


class TestTokenValidation:
    """Tests for token validation edge cases."""

    @pytest.fixture
    def handler(self) -> JWTHandler:
        """Create a JWTHandler for testing."""
        return JWTHandler(secret_key="test-secret-key-for-testing")

    def test_validate_invalid_token(self, handler: JWTHandler) -> None:
        """Should return None for invalid token."""
        claims = handler.validate_token("invalid-token")
        assert claims is None

    def test_validate_empty_token(self, handler: JWTHandler) -> None:
        """Should return None for empty token."""
        claims = handler.validate_token("")
        assert claims is None

    def test_validate_malformed_token(self, handler: JWTHandler) -> None:
        """Should return None for malformed token."""
        claims = handler.validate_token("part1.part2")
        assert claims is None

    def test_validate_token_with_wrong_secret(self) -> None:
        """Should return None for token signed with different secret."""
        handler1 = JWTHandler(secret_key="secret-key-1")
        handler2 = JWTHandler(secret_key="secret-key-2")

        token = handler1.create_access_token(user_id="user-123")
        claims = handler2.validate_token(token)

        assert claims is None

    def test_get_user_id_from_invalid_token(self, handler: JWTHandler) -> None:
        """Should return None for invalid token."""
        user_id = handler.get_user_id("invalid-token")
        assert user_id is None

    def test_get_token_type_from_invalid_token(self, handler: JWTHandler) -> None:
        """Should return None for invalid token."""
        token_type = handler.get_token_type("invalid-token")
        assert token_type is None


class TestExpiredToken:
    """Tests for expired token handling."""

    def test_validate_expired_token(self) -> None:
        """Should return None for expired token."""
        # Create handler with 0 minute expiry (immediate expiration)
        handler = JWTHandler(
            secret_key="test-secret-key-for-testing",
            access_token_expire_minutes=0,
        )

        token = handler.create_access_token(user_id="user-123")

        # Wait a moment to ensure token is expired
        time.sleep(0.1)

        claims = handler.validate_token(token)
        assert claims is None


class TestTokenExpiry:
    """Tests for token expiry time calculations."""

    def test_access_token_expire_seconds(self) -> None:
        """Should return correct access token expiry in seconds."""
        handler = JWTHandler(
            secret_key="test-secret-key",
            access_token_expire_minutes=15,
        )
        assert handler.get_access_token_expire_seconds() == 15 * 60

    def test_refresh_token_expire_seconds(self) -> None:
        """Should return correct refresh token expiry in seconds."""
        handler = JWTHandler(
            secret_key="test-secret-key",
            refresh_token_expire_days=7,
        )
        assert handler.get_refresh_token_expire_seconds() == 7 * 24 * 60 * 60

    def test_custom_expiry_values(self) -> None:
        """Should handle custom expiry values."""
        handler = JWTHandler(
            secret_key="test-secret-key",
            access_token_expire_minutes=60,
            refresh_token_expire_days=30,
        )
        assert handler.get_access_token_expire_seconds() == 60 * 60
        assert handler.get_refresh_token_expire_seconds() == 30 * 24 * 60 * 60
