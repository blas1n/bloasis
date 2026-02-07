"""
Unit tests for JWT Handler.

Tests JWT token creation, validation, and claim extraction.
Covers both RS256 (asymmetric) and HS256 (symmetric) algorithms.
"""

import tempfile
import time
from pathlib import Path

import pytest

from src.jwt_handler import JWTHandler

# =============================================================================
# Test Key Fixtures
# =============================================================================

# RSA-2048 test key pair (for testing only - do not use in production)
TEST_RSA_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCUUU9NoYWHrJXD
lix5s+XrxHVvl2a+SwvuLtyM/H3IKC658hUM2IxzF/2u16QoV6snMdPSciSdP5D9
K4N4XkfhHixpUAq+FxZxTERgIIYLw2aWEtLGTS3jsiGJ9X94PZ0iVF6/Cv/kqZqv
AO+J4Z3OvJHy2MpK/C95ot95u0ChSfUcxSnkWMt3PkWEUlcs1Adg7s/Uv+q3mBaR
tatYeRJEdgd2JEqTYPrp2ZJcJQbtaVhS4JQbFXYOAp35Tl+XLS012yUSjCgRdd43
SrV+NbsVPO0H7oE3wkB5SqaKUqJN/t9TLh4hb8e2quFF0qKx5uWQbfyI3dHiAV/u
z63VDQXfAgMBAAECggEAAUk0FGACXQsA6zFuW4JxWeTZ8npo6IexJ+ZojyFD+Ja+
0r89Bwpf1kJLNskXaUaT+1ED8rRFwsZhpsWfXfgG2qELO8Ev6G9aXctVfVKK3hl2
8ud9iwPxoFuMlKwUdi/7degSQHORhNx4CjP0/CvynFMnj+ghuqi1inIALnlZYIyc
Aa6evJq5TbUHKme7iiwPsrStKifzepcXoPYMSn0tJdDDU0FwV4aAoU56wZhXVh7J
TSYmiEwYkxccMWdsWjsmPxTbQ1K+wmeZtJ6QY4Hn7LJ49yZtTUM9mFJNosjcrGUy
0KvrDOtjFaaTXJ09ZxUi8wOWnimd5Emcdzd9zrHA8QKBgQDFid5av6kCZ9BYn9WE
G0vGI+UDnftAJ7eJK4BdR/bVpnN34Um6JeYYf0F5iG4OHIepZuKdtCc5xCbBSgL2
qcfkXdJ6gu3Q1EbXsV8fVuUg419ySR82p0BFT+bcBaeDbpDl4XwG70mf2oWmJJvH
XUNBk2erJgW1mNZhXK0QagQCKwKBgQDANk+kvhv0HeWsRZjh1CPLp8t7pRhtv0aS
yBF/4Zfs+kIfPc7U37vkARI2OldXOAwX37ls8IJRFDzl9tni7QT08REfBEBkvMVz
wJFTvlv4olF3nIsCBOZpsDGNKCLOAyEKH0TjQhIhYqfttB2enUgedtNS5mSM9f6A
2daqP+HVHQKBgQC1d5Lh0QIE6LOYRrTSGHVCv4TKDt5aMGJFy8Wva8XQvYmDzl15
eQlo5baTXAamRgVGVPLHp1EFmzFzDXete4jbPGl4DEFGP0wZJ6NX2e7BiL8M8SmQ
fpLnWaCd7T/W2MKZu8vBXx9Gj2uJlkXZHs8DNdPdgR9rlM0UQhvmYU3vYwKBgDuP
mNZf4qGeshDT8C/qYL023aMO4acAYooRXPrXmRBh7CNqL7FfMwXQHyiWo4HvaC/t
r7PGQ1uEfep0t8fN0n9kQ/3sf1e39yeLQH1Gu5EsGzqJU7nocs3FP1WSXlagOZi9
X8dcLeoSfB74dUU1T6fBAnLp2bakc5zR4+cVrJExAoGAZ0Kn2+E15XDdKn/enbL2
xP0jNzJcfL1oTPD0zslzuPDjUqL4t/SVtqx44deb/5ekGxrx0W4QyU4Cylq0u/g/
/ovWkOG6oHTiTyXna2+M7Z94xPkBwLrYdUutscif/4lhOC6Rchxzz+LLhq1yPKEy
BDZtj5c1i4uGEEcpRK18++k=
-----END PRIVATE KEY-----"""

TEST_RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAlFFPTaGFh6yVw5YsebPl
68R1b5dmvksL7i7cjPx9yCguufIVDNiMcxf9rtekKFerJzHT0nIknT+Q/SuDeF5H
4R4saVAKvhcWcUxEYCCGC8NmlhLSxk0t47IhifV/eD2dIlRevwr/5KmarwDvieGd
zryR8tjKSvwveaLfebtAoUn1HMUp5FjLdz5FhFJXLNQHYO7P1L/qt5gWkbWrWHkS
RHYHdiRKk2D66dmSXCUG7WlYUuCUGxV2DgKd+U5fly0tNdslEowoEXXeN0q1fjW7
FTztB+6BN8JAeUqmilKiTf7fUy4eIW/HtqrhRdKiseblkG38iN3R4gFf7s+t1Q0F
3wIDAQAB
-----END PUBLIC KEY-----"""


@pytest.fixture
def temp_key_dir() -> Path:
    """Create a temporary directory with RSA keys for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        key_dir = Path(tmpdir)
        # Write test keys
        (key_dir / "private.pem").write_text(TEST_RSA_PRIVATE_KEY)
        (key_dir / "public.pem").write_text(TEST_RSA_PUBLIC_KEY)
        yield key_dir


@pytest.fixture
def rsa_key_paths(temp_key_dir: Path) -> tuple[str, str]:
    """Return paths to temporary RSA key files."""
    private_path = str(temp_key_dir / "private.pem")
    public_path = str(temp_key_dir / "public.pem")
    return private_path, public_path


# =============================================================================
# HS256 Tests (Legacy Symmetric Algorithm)
# =============================================================================

class TestJWTHandlerInitHS256:
    """Tests for JWTHandler initialization with HS256 algorithm."""

    def test_init_with_valid_secret(self) -> None:
        """Should initialize with valid secret key."""
        secret = "test-secret-key-for-jwt-min-32-bytes"
        handler = JWTHandler(algorithm="HS256", secret_key=secret)
        assert handler.secret_key == secret
        assert handler.algorithm == "HS256"

    def test_init_with_custom_expiry(self) -> None:
        """Should initialize with custom expiry times."""
        handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-min-32-bytes",
            access_token_expire_minutes=30,
            refresh_token_expire_days=14,
        )
        assert handler.get_access_token_expire_seconds() == 30 * 60
        assert handler.get_refresh_token_expire_seconds() == 14 * 24 * 60 * 60

    def test_init_with_empty_secret_raises_error(self) -> None:
        """Should raise ValueError for empty secret key."""
        with pytest.raises(ValueError, match="secret key is required"):
            JWTHandler(algorithm="HS256", secret_key="")

    def test_init_with_none_secret_raises_error(self) -> None:
        """Should raise ValueError for None secret key."""
        with pytest.raises(ValueError, match="secret key is required"):
            JWTHandler(algorithm="HS256", secret_key=None)

    def test_can_sign_and_verify(self) -> None:
        """Should be able to both sign and verify with HS256."""
        handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-min-32-bytes",
        )
        assert handler.can_sign() is True
        assert handler.can_verify() is True

    def test_get_public_key_returns_none_for_hs256(self) -> None:
        """Should return None for public key with HS256."""
        handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-min-32-bytes",
        )
        assert handler.get_public_key() is None


class TestAccessTokenHS256:
    """Tests for access token creation and validation with HS256."""

    @pytest.fixture
    def handler(self) -> JWTHandler:
        """Create a JWTHandler with HS256 for testing."""
        return JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-testing-min-32-bytes",
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


class TestRefreshTokenHS256:
    """Tests for refresh token creation and validation with HS256."""

    @pytest.fixture
    def handler(self) -> JWTHandler:
        """Create a JWTHandler with HS256 for testing."""
        return JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-testing-min-32-bytes",
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


class TestTokenValidationHS256:
    """Tests for token validation edge cases with HS256."""

    @pytest.fixture
    def handler(self) -> JWTHandler:
        """Create a JWTHandler with HS256 for testing."""
        return JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-testing-min-32-bytes",
        )

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
        handler1 = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-number-one-32-bytes",
        )
        handler2 = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-number-two-32-bytes",
        )

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


# =============================================================================
# RS256 Tests (Asymmetric Algorithm)
# =============================================================================

class TestJWTHandlerInitRS256:
    """Tests for JWTHandler initialization with RS256 algorithm."""

    def test_init_with_both_keys(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should initialize with both private and public keys."""
        private_path, public_path = rsa_key_paths
        handler = JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
            public_key_path=public_path,
        )
        assert handler.algorithm == "RS256"
        assert handler.can_sign() is True
        assert handler.can_verify() is True

    def test_init_with_private_key_only(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should initialize with only private key (for signing)."""
        private_path, _ = rsa_key_paths
        handler = JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
        )
        assert handler.can_sign() is True
        assert handler.can_verify() is False

    def test_init_with_public_key_only(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should initialize with only public key (for verification)."""
        _, public_path = rsa_key_paths
        handler = JWTHandler(
            algorithm="RS256",
            public_key_path=public_path,
        )
        assert handler.can_sign() is False
        assert handler.can_verify() is True

    def test_init_without_keys_raises_error(self) -> None:
        """Should raise ValueError when no keys provided for RS256."""
        with pytest.raises(ValueError, match="requires private_key_path and/or public_key_path"):
            JWTHandler(algorithm="RS256")

    def test_init_with_nonexistent_private_key_raises_error(self) -> None:
        """Should raise FileNotFoundError for nonexistent private key."""
        with pytest.raises(FileNotFoundError, match="Key file not found"):
            JWTHandler(
                algorithm="RS256",
                private_key_path="/nonexistent/path/private.pem",
            )

    def test_init_with_nonexistent_public_key_raises_error(self) -> None:
        """Should raise FileNotFoundError for nonexistent public key."""
        with pytest.raises(FileNotFoundError, match="Key file not found"):
            JWTHandler(
                algorithm="RS256",
                public_key_path="/nonexistent/path/public.pem",
            )

    def test_init_with_empty_key_file_raises_error(self, temp_key_dir: Path) -> None:
        """Should raise ValueError for empty key file."""
        empty_key_path = temp_key_dir / "empty.pem"
        empty_key_path.write_text("")
        with pytest.raises(ValueError, match="Key file is empty"):
            JWTHandler(
                algorithm="RS256",
                private_key_path=str(empty_key_path),
            )

    def test_get_public_key_returns_key_content(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should return public key content for RS256."""
        private_path, public_path = rsa_key_paths
        handler = JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
            public_key_path=public_path,
        )
        public_key = handler.get_public_key()
        assert public_key is not None
        assert "BEGIN PUBLIC KEY" in public_key

    def test_secret_key_is_none_for_rs256(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should have None secret_key for RS256 (backward compatibility)."""
        private_path, public_path = rsa_key_paths
        handler = JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
            public_key_path=public_path,
        )
        assert handler.secret_key is None


class TestAccessTokenRS256:
    """Tests for access token creation and validation with RS256."""

    @pytest.fixture
    def handler(self, rsa_key_paths: tuple[str, str]) -> JWTHandler:
        """Create a JWTHandler with RS256 for testing."""
        private_path, public_path = rsa_key_paths
        return JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
            public_key_path=public_path,
            access_token_expire_minutes=15,
        )

    def test_create_access_token(self, handler: JWTHandler) -> None:
        """Should create valid access token with RS256."""
        token = handler.create_access_token(user_id="user-123")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_validate_access_token(self, handler: JWTHandler) -> None:
        """Should validate and return claims from RS256 access token."""
        token = handler.create_access_token(user_id="user-123")
        claims = handler.validate_token(token)

        assert claims is not None
        assert claims["sub"] == "user-123"
        assert claims["type"] == "access"

    def test_create_access_token_with_additional_claims(self, handler: JWTHandler) -> None:
        """Should create RS256 access token with additional claims."""
        token = handler.create_access_token(
            user_id="user-123",
            additional_claims={"role": "admin"},
        )
        claims = handler.validate_token(token)
        assert claims is not None
        assert claims["role"] == "admin"


class TestRefreshTokenRS256:
    """Tests for refresh token creation and validation with RS256."""

    @pytest.fixture
    def handler(self, rsa_key_paths: tuple[str, str]) -> JWTHandler:
        """Create a JWTHandler with RS256 for testing."""
        private_path, public_path = rsa_key_paths
        return JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
            public_key_path=public_path,
            refresh_token_expire_days=7,
        )

    def test_create_refresh_token(self, handler: JWTHandler) -> None:
        """Should create valid refresh token with RS256."""
        token = handler.create_refresh_token(user_id="user-123")
        assert token is not None
        assert isinstance(token, str)

    def test_validate_refresh_token(self, handler: JWTHandler) -> None:
        """Should validate and return claims from RS256 refresh token."""
        token = handler.create_refresh_token(user_id="user-123")
        claims = handler.validate_token(token)

        assert claims is not None
        assert claims["sub"] == "user-123"
        assert claims["type"] == "refresh"


class TestTokenValidationRS256:
    """Tests for token validation edge cases with RS256."""

    def test_cannot_sign_without_private_key(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should raise error when trying to sign without private key."""
        _, public_path = rsa_key_paths
        handler = JWTHandler(
            algorithm="RS256",
            public_key_path=public_path,
        )
        with pytest.raises(ValueError, match="Signing key not available"):
            handler.create_access_token(user_id="user-123")

    def test_cannot_verify_without_public_key(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should return None when verifying without public key."""
        private_path, _ = rsa_key_paths
        handler = JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
        )
        token = handler.create_access_token(user_id="user-123")
        # Cannot verify without public key
        claims = handler.validate_token(token)
        assert claims is None

    def test_validate_hs256_token_with_rs256_handler_fails(
        self, rsa_key_paths: tuple[str, str]
    ) -> None:
        """Should fail when validating HS256 token with RS256 handler."""
        hs256_handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-min-32-bytes",
        )
        hs256_token = hs256_handler.create_access_token(user_id="user-123")

        private_path, public_path = rsa_key_paths
        rs256_handler = JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
            public_key_path=public_path,
        )
        claims = rs256_handler.validate_token(hs256_token)
        assert claims is None


# =============================================================================
# Cross-Algorithm Tests
# =============================================================================

class TestCrossAlgorithmValidation:
    """Tests for cross-algorithm token validation."""

    def test_rs256_token_cannot_be_validated_with_hs256(
        self, rsa_key_paths: tuple[str, str]
    ) -> None:
        """RS256 token should not validate with HS256 handler."""
        private_path, public_path = rsa_key_paths
        rs256_handler = JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
            public_key_path=public_path,
        )
        rs256_token = rs256_handler.create_access_token(user_id="user-123")

        hs256_handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-min-32-bytes",
        )
        claims = hs256_handler.validate_token(rs256_token)
        assert claims is None


# =============================================================================
# Token Expiry Tests
# =============================================================================

class TestExpiredToken:
    """Tests for expired token handling."""

    def test_validate_expired_token_hs256(self) -> None:
        """Should return None for expired HS256 token."""
        handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-testing-min-32-bytes",
            access_token_expire_minutes=0,
        )

        token = handler.create_access_token(user_id="user-123")
        time.sleep(0.1)  # Wait for token to expire

        claims = handler.validate_token(token)
        assert claims is None

    def test_validate_expired_token_rs256(self, rsa_key_paths: tuple[str, str]) -> None:
        """Should return None for expired RS256 token."""
        private_path, public_path = rsa_key_paths
        handler = JWTHandler(
            algorithm="RS256",
            private_key_path=private_path,
            public_key_path=public_path,
            access_token_expire_minutes=0,
        )

        token = handler.create_access_token(user_id="user-123")
        time.sleep(0.1)  # Wait for token to expire

        claims = handler.validate_token(token)
        assert claims is None


class TestTokenExpiry:
    """Tests for token expiry time calculations."""

    def test_access_token_expire_seconds(self) -> None:
        """Should return correct access token expiry in seconds."""
        handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-min-32-bytes",
            access_token_expire_minutes=15,
        )
        assert handler.get_access_token_expire_seconds() == 15 * 60

    def test_refresh_token_expire_seconds(self) -> None:
        """Should return correct refresh token expiry in seconds."""
        handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-min-32-bytes",
            refresh_token_expire_days=7,
        )
        assert handler.get_refresh_token_expire_seconds() == 7 * 24 * 60 * 60

    def test_custom_expiry_values(self) -> None:
        """Should handle custom expiry values."""
        handler = JWTHandler(
            algorithm="HS256",
            secret_key="test-secret-key-for-jwt-min-32-bytes",
            access_token_expire_minutes=60,
            refresh_token_expire_days=30,
        )
        assert handler.get_access_token_expire_seconds() == 60 * 60
        assert handler.get_refresh_token_expire_seconds() == 30 * 24 * 60 * 60


# =============================================================================
# Unsupported Algorithm Tests
# =============================================================================

class TestUnsupportedAlgorithm:
    """Tests for unsupported algorithm handling."""

    def test_unsupported_algorithm_raises_error(self) -> None:
        """Should raise ValueError for unsupported algorithm."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            JWTHandler(
                algorithm="HS512",
                secret_key="test-secret",
            )
