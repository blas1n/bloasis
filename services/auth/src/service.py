"""
Auth Service - gRPC Servicer Implementation.

Implements the AuthService gRPC interface with:
- Login: Validate credentials via User Service, issue JWT tokens
- ValidateToken: Verify JWT access tokens
- RefreshToken: Issue new access token using refresh token
- Logout: Invalidate refresh token via Redis
"""

import logging
from typing import Optional

import grpc
from shared.generated import auth_pb2, auth_pb2_grpc
from shared.utils import RedisClient

from .clients.user_client import UserClient
from .jwt_handler import JWTHandler

logger = logging.getLogger(__name__)


def _refresh_token_key(user_id: str) -> str:
    """Generate Redis key for refresh token.

    Args:
        user_id: User identifier.

    Returns:
        Redis key for the user's refresh token.
    """
    return f"refresh_token:{user_id}"


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):
    """
    gRPC servicer implementing the AuthService interface.

    Provides JWT authentication with:
    - User Service integration for credential validation
    - Redis storage for refresh tokens
    - Kong JWT Plugin compatibility
    """

    def __init__(
        self,
        jwt_handler: JWTHandler,
        redis_client: Optional[RedisClient] = None,
        user_client: Optional[UserClient] = None,
    ) -> None:
        """
        Initialize the servicer with required dependencies.

        Args:
            jwt_handler: JWT handler for token operations.
            redis_client: Redis client for refresh token storage.
            user_client: User Service client for credential validation.
        """
        self.jwt = jwt_handler
        self.redis = redis_client
        self.user_client = user_client

    async def Login(
        self,
        request: auth_pb2.LoginRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.LoginResponse:
        """
        Authenticate user credentials and return JWT tokens.

        Validates credentials via User Service, then issues
        access and refresh tokens if valid.

        Args:
            request: The gRPC request containing email and password.
            context: The gRPC servicer context.

        Returns:
            LoginResponse with tokens if successful, error message otherwise.
        """
        try:
            email = request.email
            password = request.password

            # Validate required fields
            if not email:
                logger.debug("Login failed: email is required")
                return auth_pb2.LoginResponse(
                    success=False,
                    error_message="email is required",
                )

            if not password:
                logger.debug("Login failed: password is required")
                return auth_pb2.LoginResponse(
                    success=False,
                    error_message="password is required",
                )

            # Validate credentials via User Service
            if not self.user_client:
                logger.error("User client not initialized")
                return auth_pb2.LoginResponse(
                    success=False,
                    error_message="Authentication service unavailable",
                )

            try:
                valid, user_id = await self.user_client.validate_credentials(email, password)
            except (ConnectionError, TimeoutError) as e:
                logger.error(f"Failed to validate credentials: {e}")
                return auth_pb2.LoginResponse(
                    success=False,
                    error_message="Authentication service unavailable",
                )

            if not valid or not user_id:
                logger.info("Login failed: invalid credentials for email")
                return auth_pb2.LoginResponse(
                    success=False,
                    error_message="Invalid email or password",
                )

            # Create tokens
            access_token = self.jwt.create_access_token(user_id)
            refresh_token = self.jwt.create_refresh_token(user_id)
            expires_in = self.jwt.get_access_token_expire_seconds()

            # Store refresh token in Redis
            if self.redis:
                refresh_key = _refresh_token_key(user_id)
                refresh_ttl = self.jwt.get_refresh_token_expire_seconds()
                await self.redis.setex(refresh_key, refresh_ttl, refresh_token)
                logger.debug(f"Stored refresh token for user: {user_id}")

            logger.info(f"Login successful for user: {user_id}")
            return auth_pb2.LoginResponse(
                success=True,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                user_id=user_id,
            )

        except Exception as e:
            logger.error(f"Login error: {e}")
            return auth_pb2.LoginResponse(
                success=False,
                error_message="Internal authentication error",
            )

    async def ValidateToken(
        self,
        request: auth_pb2.ValidateTokenRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ValidateTokenResponse:
        """
        Validate a JWT access token.

        Verifies token signature, expiry, and type.

        Args:
            request: The gRPC request containing the token.
            context: The gRPC servicer context.

        Returns:
            ValidateTokenResponse with validation result.
        """
        try:
            token = request.token

            if not token:
                return auth_pb2.ValidateTokenResponse(
                    valid=False,
                    error_message="token is required",
                )

            # Validate token
            claims = self.jwt.validate_token(token)

            if not claims:
                return auth_pb2.ValidateTokenResponse(
                    valid=False,
                    error_message="Invalid or expired token",
                )

            # Check token type
            token_type = claims.get("type")
            if token_type != "access":
                return auth_pb2.ValidateTokenResponse(
                    valid=False,
                    error_message="Invalid token type",
                )

            user_id = claims.get("sub", "")
            logger.debug(f"Token validated for user: {user_id}")

            return auth_pb2.ValidateTokenResponse(
                valid=True,
                user_id=user_id,
            )

        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return auth_pb2.ValidateTokenResponse(
                valid=False,
                error_message="Token validation failed",
            )

    async def RefreshToken(
        self,
        request: auth_pb2.RefreshTokenRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.RefreshTokenResponse:
        """
        Issue a new access token using a refresh token.

        Validates the refresh token and checks it against Redis storage.

        Args:
            request: The gRPC request containing the refresh token.
            context: The gRPC servicer context.

        Returns:
            RefreshTokenResponse with new access token if successful.
        """
        try:
            refresh_token = request.refresh_token

            if not refresh_token:
                return auth_pb2.RefreshTokenResponse(
                    success=False,
                    error_message="refresh_token is required",
                )

            # Validate refresh token
            claims = self.jwt.validate_token(refresh_token)

            if not claims:
                return auth_pb2.RefreshTokenResponse(
                    success=False,
                    error_message="Invalid or expired refresh token",
                )

            # Check token type
            token_type = claims.get("type")
            if token_type != "refresh":
                return auth_pb2.RefreshTokenResponse(
                    success=False,
                    error_message="Invalid token type",
                )

            user_id = claims.get("sub", "")

            # Verify refresh token is stored in Redis (not revoked)
            if self.redis:
                refresh_key = _refresh_token_key(user_id)
                stored_token = await self.redis.get(refresh_key)

                if not stored_token:
                    logger.info(f"Refresh token not found in Redis for user: {user_id}")
                    return auth_pb2.RefreshTokenResponse(
                        success=False,
                        error_message="Refresh token has been revoked",
                    )

                # Compare tokens (stored_token might be bytes or str)
                if isinstance(stored_token, bytes):
                    stored_token = stored_token.decode("utf-8")

                if stored_token != refresh_token:
                    logger.info(f"Refresh token mismatch for user: {user_id}")
                    return auth_pb2.RefreshTokenResponse(
                        success=False,
                        error_message="Invalid refresh token",
                    )

            # Create new access token
            access_token = self.jwt.create_access_token(user_id)
            expires_in = self.jwt.get_access_token_expire_seconds()

            logger.info(f"Access token refreshed for user: {user_id}")
            return auth_pb2.RefreshTokenResponse(
                success=True,
                access_token=access_token,
                expires_in=expires_in,
            )

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return auth_pb2.RefreshTokenResponse(
                success=False,
                error_message="Token refresh failed",
            )

    async def Logout(
        self,
        request: auth_pb2.LogoutRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.LogoutResponse:
        """
        Invalidate a refresh token (logout).

        Removes the refresh token from Redis storage.

        Args:
            request: The gRPC request containing the refresh token.
            context: The gRPC servicer context.

        Returns:
            LogoutResponse indicating success.
        """
        try:
            refresh_token = request.refresh_token

            if not refresh_token:
                return auth_pb2.LogoutResponse(success=False)

            # Validate refresh token to get user_id
            claims = self.jwt.validate_token(refresh_token)

            if not claims:
                # Token is invalid or expired, but we still return success
                # as the user is effectively logged out
                return auth_pb2.LogoutResponse(success=True)

            user_id = claims.get("sub", "")

            # Remove refresh token from Redis
            if self.redis and user_id:
                refresh_key = _refresh_token_key(user_id)
                await self.redis.delete(refresh_key)
                logger.info(f"Logout successful for user: {user_id}")

            return auth_pb2.LogoutResponse(success=True)

        except Exception as e:
            logger.error(f"Logout error: {e}")
            return auth_pb2.LogoutResponse(success=False)
