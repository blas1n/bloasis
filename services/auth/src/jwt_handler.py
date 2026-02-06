"""JWT token handling for authentication.

Handles JWT token creation, validation, and claim extraction.
Uses PyJWT for JWT operations with HS256 algorithm.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

logger = logging.getLogger(__name__)


class JWTHandler:
    """Handles JWT token creation and validation."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
    ) -> None:
        """Initialize JWT handler.

        Args:
            secret_key: Secret key for signing tokens.
            algorithm: JWT signing algorithm (default: HS256).
            access_token_expire_minutes: Access token expiry in minutes.
            refresh_token_expire_days: Refresh token expiry in days.

        Raises:
            ValueError: If secret_key is empty.
        """
        if not secret_key:
            raise ValueError("JWT secret key is required")

        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_expire = timedelta(days=refresh_token_expire_days)

    def create_access_token(
        self,
        user_id: str,
        additional_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create JWT access token.

        Args:
            user_id: User identifier to include in token.
            additional_claims: Optional additional claims to include.

        Returns:
            Encoded JWT access token.
        """
        now = datetime.now(timezone.utc)
        claims: dict[str, Any] = {
            "sub": user_id,
            "type": "access",
            "exp": now + self.access_expire,
            "iat": now,
        }
        if additional_claims:
            claims.update(additional_claims)

        token = jwt.encode(claims, self.secret_key, algorithm=self.algorithm)
        logger.debug(f"Created access token for user: {user_id}")
        return token

    def create_refresh_token(self, user_id: str) -> str:
        """Create JWT refresh token.

        Args:
            user_id: User identifier to include in token.

        Returns:
            Encoded JWT refresh token.
        """
        now = datetime.now(timezone.utc)
        claims: dict[str, Any] = {
            "sub": user_id,
            "type": "refresh",
            "exp": now + self.refresh_expire,
            "iat": now,
        }
        token = jwt.encode(claims, self.secret_key, algorithm=self.algorithm)
        logger.debug(f"Created refresh token for user: {user_id}")
        return token

    def validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate JWT token and return claims.

        Args:
            token: JWT token to validate.

        Returns:
            Token claims if valid, None if invalid or expired.
        """
        try:
            claims = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return claims
        except jwt.ExpiredSignatureError:
            logger.debug("Token validation failed: expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug(f"Token validation failed: {e}")
            return None

    def get_user_id(self, token: str) -> str | None:
        """Extract user_id from token.

        Args:
            token: JWT token to extract user_id from.

        Returns:
            User ID if token is valid, None otherwise.
        """
        claims = self.validate_token(token)
        return claims.get("sub") if claims else None

    def get_token_type(self, token: str) -> str | None:
        """Extract token type from token.

        Args:
            token: JWT token to extract type from.

        Returns:
            Token type ('access' or 'refresh') if valid, None otherwise.
        """
        claims = self.validate_token(token)
        return claims.get("type") if claims else None

    def get_access_token_expire_seconds(self) -> int:
        """Get access token expiry in seconds.

        Returns:
            Access token expiry duration in seconds.
        """
        return int(self.access_expire.total_seconds())

    def get_refresh_token_expire_seconds(self) -> int:
        """Get refresh token expiry in seconds.

        Returns:
            Refresh token expiry duration in seconds.
        """
        return int(self.refresh_expire.total_seconds())
