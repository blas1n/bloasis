"""JWT token handling for authentication.

Handles JWT token creation, validation, and claim extraction.
Uses RS256 (asymmetric) algorithm exclusively:
- Private key stays in Auth Service (signing only)
- Public key distributed to Envoy Gateway and other services (verification)
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt

logger = logging.getLogger(__name__)


class JWTHandler:
    """Handles JWT token creation and validation using RS256.

    RS256 uses asymmetric RSA keys:
    - Private key for signing (required for token creation)
    - Public key for verification (required for token validation)

    Either key can be omitted if the corresponding operation is not needed.
    """

    def __init__(
        self,
        private_key_path: str | None = None,
        public_key_path: str | None = None,
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
    ) -> None:
        """Initialize JWT handler.

        Args:
            private_key_path: Path to RSA private key file (for signing).
            public_key_path: Path to RSA public key file (for verification).
            access_token_expire_minutes: Access token expiry in minutes.
            refresh_token_expire_days: Refresh token expiry in days.

        Raises:
            ValueError: If neither key path is provided, or if key files are invalid.
            FileNotFoundError: If key files do not exist.
        """
        if not private_key_path and not public_key_path:
            raise ValueError(
                "RS256 algorithm requires private_key_path and/or public_key_path"
            )

        self.algorithm = "RS256"
        self.access_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_expire = timedelta(days=refresh_token_expire_days)

        self._private_key = self._load_key(private_key_path) if private_key_path else None
        self._public_key = self._load_key(public_key_path) if public_key_path else None

        self._signing_key = self._private_key
        self._verify_key = self._public_key

    def _load_key(self, key_path: str) -> str:
        """Load a key from file.

        Args:
            key_path: Path to the key file.

        Returns:
            Key content as string.

        Raises:
            FileNotFoundError: If key file does not exist.
            ValueError: If key file is empty or invalid.
        """
        path = Path(key_path)
        if not path.exists():
            raise FileNotFoundError(f"Key file not found: {key_path}")

        key_content = path.read_text().strip()
        if not key_content:
            raise ValueError(f"Key file is empty: {key_path}")

        logger.debug(f"Loaded key from: {key_path}")
        return key_content

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

        Raises:
            ValueError: If signing key is not available.
        """
        if self._signing_key is None:
            raise ValueError("Signing key not available. Private key required for RS256.")

        now = datetime.now(timezone.utc)
        claims: dict[str, Any] = {
            "sub": user_id,
            "type": "access",
            "exp": now + self.access_expire,
            "iat": now,
        }
        if additional_claims:
            claims.update(additional_claims)

        token = jwt.encode(claims, self._signing_key, algorithm=self.algorithm)
        logger.debug(f"Created access token for user: {user_id}")
        return token

    def create_refresh_token(self, user_id: str) -> str:
        """Create JWT refresh token.

        Args:
            user_id: User identifier to include in token.

        Returns:
            Encoded JWT refresh token.

        Raises:
            ValueError: If signing key is not available.
        """
        if self._signing_key is None:
            raise ValueError("Signing key not available. Private key required for RS256.")

        now = datetime.now(timezone.utc)
        claims: dict[str, Any] = {
            "sub": user_id,
            "type": "refresh",
            "exp": now + self.refresh_expire,
            "iat": now,
        }
        token = jwt.encode(claims, self._signing_key, algorithm=self.algorithm)
        logger.debug(f"Created refresh token for user: {user_id}")
        return token

    def validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate JWT token and return claims.

        Args:
            token: JWT token to validate.

        Returns:
            Token claims if valid, None if invalid or expired.
        """
        if self._verify_key is None:
            logger.error("Verification key not available")
            return None

        try:
            claims = jwt.decode(token, self._verify_key, algorithms=[self.algorithm])
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

    def get_public_key(self) -> str | None:
        """Get the public key for RS256 algorithm.

        Can be used to share the public key with Envoy Gateway
        and other services for token verification.

        Returns:
            Public key content, or None if not loaded.
        """
        return self._public_key

    def can_sign(self) -> bool:
        """Check if this handler can sign tokens.

        Returns:
            True if private key is available, False otherwise.
        """
        return self._signing_key is not None

    def can_verify(self) -> bool:
        """Check if this handler can verify tokens.

        Returns:
            True if public key is available, False otherwise.
        """
        return self._verify_key is not None
