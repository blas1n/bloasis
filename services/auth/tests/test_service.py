"""
Unit tests for Auth Service.

All external dependencies (Redis, User Service) are mocked.
Target: 80%+ code coverage.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.jwt_handler import JWTHandler


class TestAuthServicerLogin:
    """Tests for Login gRPC method."""

    @pytest.fixture
    def jwt_handler(self) -> JWTHandler:
        """Create JWT handler for testing."""
        return JWTHandler(
            secret_key="test-secret-key-for-jwt-testing-min-32-bytes",
            algorithm="HS256",
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
        )

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.setex = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_user_client(self) -> AsyncMock:
        """Create mock User Service client."""
        mock = AsyncMock()
        mock.validate_credentials = AsyncMock(return_value=(False, ""))
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_login_success(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_user_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return tokens on successful login."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        mock_user_client.validate_credentials.return_value = (True, "user-123")

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
            user_client=mock_user_client,
        )

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="securepassword",
        )
        response = await servicer.Login(request, mock_context)

        assert response.success is True
        assert response.access_token != ""
        assert response.refresh_token != ""
        assert response.expires_in == 15 * 60
        assert response.user_id == "user-123"
        assert response.error_message == ""
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_missing_email(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_user_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when email is missing."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
            user_client=mock_user_client,
        )

        request = auth_pb2.LoginRequest(email="", password="password")
        response = await servicer.Login(request, mock_context)

        assert response.success is False
        assert response.error_message == "email is required"

    @pytest.mark.asyncio
    async def test_login_missing_password(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_user_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when password is missing."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
            user_client=mock_user_client,
        )

        request = auth_pb2.LoginRequest(email="test@example.com", password="")
        response = await servicer.Login(request, mock_context)

        assert response.success is False
        assert response.error_message == "password is required"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_user_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error for invalid credentials."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        mock_user_client.validate_credentials.return_value = (False, "")

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
            user_client=mock_user_client,
        )

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="wrongpassword",
        )
        response = await servicer.Login(request, mock_context)

        assert response.success is False
        assert response.error_message == "Invalid email or password"

    @pytest.mark.asyncio
    async def test_login_user_service_unavailable(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_user_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when User Service is unavailable."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        mock_user_client.validate_credentials.side_effect = ConnectionError("Service unavailable")

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
            user_client=mock_user_client,
        )

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="password",
        )
        response = await servicer.Login(request, mock_context)

        assert response.success is False
        assert response.error_message == "Authentication service unavailable"

    @pytest.mark.asyncio
    async def test_login_user_service_timeout(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_user_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when User Service times out."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        mock_user_client.validate_credentials.side_effect = TimeoutError("Request timed out")

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
            user_client=mock_user_client,
        )

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="password",
        )
        response = await servicer.Login(request, mock_context)

        assert response.success is False
        assert response.error_message == "Authentication service unavailable"

    @pytest.mark.asyncio
    async def test_login_no_user_client(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when user client is not initialized."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
            user_client=None,
        )

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="password",
        )
        response = await servicer.Login(request, mock_context)

        assert response.success is False
        assert response.error_message == "Authentication service unavailable"

    @pytest.mark.asyncio
    async def test_login_without_redis(
        self,
        jwt_handler: JWTHandler,
        mock_user_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should work without Redis client (no refresh token storage)."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        mock_user_client.validate_credentials.return_value = (True, "user-123")

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=None,
            user_client=mock_user_client,
        )

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="password",
        )
        response = await servicer.Login(request, mock_context)

        assert response.success is True
        assert response.access_token != ""


class TestAuthServicerValidateToken:
    """Tests for ValidateToken gRPC method."""

    @pytest.fixture
    def jwt_handler(self) -> JWTHandler:
        """Create JWT handler for testing."""
        return JWTHandler(secret_key="test-secret-key-for-jwt-testing-min-32-bytes", algorithm="HS256")

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_validate_token_success(
        self,
        jwt_handler: JWTHandler,
        mock_context: MagicMock,
    ) -> None:
        """Should return valid=true for valid access token."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(jwt_handler=jwt_handler)

        access_token = jwt_handler.create_access_token(user_id="user-123")
        request = auth_pb2.ValidateTokenRequest(token=access_token)
        response = await servicer.ValidateToken(request, mock_context)

        assert response.valid is True
        assert response.user_id == "user-123"
        assert response.error_message == ""

    @pytest.mark.asyncio
    async def test_validate_token_missing(
        self,
        jwt_handler: JWTHandler,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when token is missing."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(jwt_handler=jwt_handler)

        request = auth_pb2.ValidateTokenRequest(token="")
        response = await servicer.ValidateToken(request, mock_context)

        assert response.valid is False
        assert response.error_message == "token is required"

    @pytest.mark.asyncio
    async def test_validate_token_invalid(
        self,
        jwt_handler: JWTHandler,
        mock_context: MagicMock,
    ) -> None:
        """Should return valid=false for invalid token."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(jwt_handler=jwt_handler)

        request = auth_pb2.ValidateTokenRequest(token="invalid-token")
        response = await servicer.ValidateToken(request, mock_context)

        assert response.valid is False
        assert response.error_message == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_validate_token_wrong_type(
        self,
        jwt_handler: JWTHandler,
        mock_context: MagicMock,
    ) -> None:
        """Should return error for refresh token (wrong type)."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(jwt_handler=jwt_handler)

        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")
        request = auth_pb2.ValidateTokenRequest(token=refresh_token)
        response = await servicer.ValidateToken(request, mock_context)

        assert response.valid is False
        assert response.error_message == "Invalid token type"


class TestAuthServicerRefreshToken:
    """Tests for RefreshToken gRPC method."""

    @pytest.fixture
    def jwt_handler(self) -> JWTHandler:
        """Create JWT handler for testing."""
        return JWTHandler(secret_key="test-secret-key-for-jwt-testing-min-32-bytes", algorithm="HS256")

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_refresh_token_success(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return new access token for valid refresh token."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")
        mock_redis.get.return_value = refresh_token

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        request = auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is True
        assert response.access_token != ""
        assert response.expires_in == jwt_handler.get_access_token_expire_seconds()
        assert response.error_message == ""

    @pytest.mark.asyncio
    async def test_refresh_token_success_with_bytes(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should handle refresh token stored as bytes in Redis."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")
        mock_redis.get.return_value = refresh_token.encode("utf-8")

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        request = auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is True
        assert response.access_token != ""

    @pytest.mark.asyncio
    async def test_refresh_token_missing(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when refresh token is missing."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        request = auth_pb2.RefreshTokenRequest(refresh_token="")
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is False
        assert response.error_message == "refresh_token is required"

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error for invalid refresh token."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        request = auth_pb2.RefreshTokenRequest(refresh_token="invalid-token")
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is False
        assert response.error_message == "Invalid or expired refresh token"

    @pytest.mark.asyncio
    async def test_refresh_token_wrong_type(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error for access token (wrong type)."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        access_token = jwt_handler.create_access_token(user_id="user-123")
        request = auth_pb2.RefreshTokenRequest(refresh_token=access_token)
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is False
        assert response.error_message == "Invalid token type"

    @pytest.mark.asyncio
    async def test_refresh_token_revoked(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when refresh token is revoked (not in Redis)."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        mock_redis.get.return_value = None

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")
        request = auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is False
        assert response.error_message == "Refresh token has been revoked"

    @pytest.mark.asyncio
    async def test_refresh_token_mismatch(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when refresh token doesn't match stored token."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        # Create token for one user (stored in Redis)
        stored_token = jwt_handler.create_refresh_token(user_id="user-123")
        # Create a different token by using a different user
        # but the request claims to be from user-123
        different_user_handler = JWTHandler(
            secret_key="test-secret-key-for-jwt-testing-min-32-bytes",  # Same secret
            algorithm="HS256",
        )
        different_token = different_user_handler.create_refresh_token(user_id="user-456")
        # But we'll check against user-123's stored token
        mock_redis.get.return_value = stored_token

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        # The token is valid but for a different user - so when we look up
        # user-456's refresh token key, we get user-123's token which won't match
        request = auth_pb2.RefreshTokenRequest(refresh_token=different_token)
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is False
        assert response.error_message == "Invalid refresh token"

    @pytest.mark.asyncio
    async def test_refresh_token_without_redis(
        self,
        jwt_handler: JWTHandler,
        mock_context: MagicMock,
    ) -> None:
        """Should work without Redis client (no revocation check)."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=None,
        )

        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")
        request = auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is True
        assert response.access_token != ""


class TestAuthServicerLogout:
    """Tests for Logout gRPC method."""

    @pytest.fixture
    def jwt_handler(self) -> JWTHandler:
        """Create JWT handler for testing."""
        return JWTHandler(secret_key="test-secret-key-for-jwt-testing-min-32-bytes", algorithm="HS256")

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_logout_success(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should delete refresh token from Redis on logout."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")
        request = auth_pb2.LogoutRequest(refresh_token=refresh_token)
        response = await servicer.Logout(request, mock_context)

        assert response.success is True
        mock_redis.delete.assert_called_once_with("refresh_token:user-123")

    @pytest.mark.asyncio
    async def test_logout_missing_token(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return success=false when token is missing."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        request = auth_pb2.LogoutRequest(refresh_token="")
        response = await servicer.Logout(request, mock_context)

        assert response.success is False

    @pytest.mark.asyncio
    async def test_logout_invalid_token(
        self,
        jwt_handler: JWTHandler,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return success=true for invalid token (user is logged out)."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=mock_redis,
        )

        request = auth_pb2.LogoutRequest(refresh_token="invalid-token")
        response = await servicer.Logout(request, mock_context)

        assert response.success is True

    @pytest.mark.asyncio
    async def test_logout_without_redis(
        self,
        jwt_handler: JWTHandler,
        mock_context: MagicMock,
    ) -> None:
        """Should work without Redis client."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            redis_client=None,
        )

        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")
        request = auth_pb2.LogoutRequest(refresh_token=refresh_token)
        response = await servicer.Logout(request, mock_context)

        assert response.success is True


class TestServiceHelperFunctions:
    """Tests for service helper functions."""

    def test_refresh_token_key(self) -> None:
        """Should generate correct Redis key for refresh token."""
        from src.service import _refresh_token_key

        key = _refresh_token_key("user-123")
        assert key == "refresh_token:user-123"


class TestServicerErrors:
    """Test error handling in servicer."""

    @pytest.fixture
    def jwt_handler(self) -> JWTHandler:
        """Create JWT handler for testing."""
        return JWTHandler(secret_key="test-secret-key-for-jwt-testing-min-32-bytes", algorithm="HS256")

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_login_exception(
        self,
        jwt_handler: JWTHandler,
        mock_context: MagicMock,
    ) -> None:
        """Should handle exceptions gracefully in login."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        mock_user_client = AsyncMock()
        mock_user_client.validate_credentials.side_effect = Exception("Unexpected error")

        servicer = AuthServicer(
            jwt_handler=jwt_handler,
            user_client=mock_user_client,
        )

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="password",
        )
        response = await servicer.Login(request, mock_context)

        assert response.success is False
        assert response.error_message == "Internal authentication error"

    @pytest.mark.asyncio
    async def test_validate_token_exception(
        self,
        mock_context: MagicMock,
    ) -> None:
        """Should handle exceptions gracefully in validate token."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        # Create a mock JWT handler that raises an exception
        mock_jwt_handler = MagicMock()
        mock_jwt_handler.validate_token.side_effect = Exception("Unexpected error")

        servicer = AuthServicer(jwt_handler=mock_jwt_handler)

        request = auth_pb2.ValidateTokenRequest(token="some-token")
        response = await servicer.ValidateToken(request, mock_context)

        assert response.valid is False
        assert response.error_message == "Token validation failed"

    @pytest.mark.asyncio
    async def test_refresh_token_exception(
        self,
        mock_context: MagicMock,
    ) -> None:
        """Should handle exceptions gracefully in refresh token."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        # Create a mock JWT handler that raises an exception
        mock_jwt_handler = MagicMock()
        mock_jwt_handler.validate_token.side_effect = Exception("Unexpected error")

        servicer = AuthServicer(jwt_handler=mock_jwt_handler)

        request = auth_pb2.RefreshTokenRequest(refresh_token="some-token")
        response = await servicer.RefreshToken(request, mock_context)

        assert response.success is False
        assert response.error_message == "Token refresh failed"

    @pytest.mark.asyncio
    async def test_logout_exception(
        self,
        mock_context: MagicMock,
    ) -> None:
        """Should handle exceptions gracefully in logout."""
        from shared.generated import auth_pb2

        from src.service import AuthServicer

        # Create a mock JWT handler that raises an exception
        mock_jwt_handler = MagicMock()
        mock_jwt_handler.validate_token.side_effect = Exception("Unexpected error")

        servicer = AuthServicer(jwt_handler=mock_jwt_handler)

        request = auth_pb2.LogoutRequest(refresh_token="some-token")
        response = await servicer.Logout(request, mock_context)

        assert response.success is False


class TestMainModule:
    """Tests for main.py module."""

    @pytest.mark.asyncio
    async def test_serve_initializes_clients(self) -> None:
        """Should initialize all clients on serve."""
        import asyncio
        from unittest.mock import patch

        # Import the module first so patches work correctly
        import src.main as main_module

        with (
            patch.object(main_module, "RedisClient") as mock_redis_cls,
            patch.object(main_module, "UserClient") as mock_user_cls,
            patch.object(main_module, "grpc") as mock_grpc,
            patch.object(main_module, "health") as mock_health_module,
            patch.object(main_module, "health_pb2") as mock_health_pb2,
            patch.object(main_module, "health_pb2_grpc"),
            patch.object(main_module, "auth_pb2_grpc"),
            patch.object(main_module, "config") as mock_config,
        ):
            # Setup mocks
            mock_config.service_name = "auth-test"
            mock_config.grpc_port = 50059
            mock_config.consul_enabled = False
            mock_config.jwt_secret_key = "test-secret-key-for-jwt-testing-min-32-bytes"
            mock_config.jwt_algorithm = "HS256"
            mock_config.access_token_expire_minutes = 15
            mock_config.refresh_token_expire_days = 7

            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            mock_user = AsyncMock()
            mock_user_cls.return_value = mock_user

            mock_server = MagicMock()
            mock_server.add_insecure_port = MagicMock()
            mock_server.start = AsyncMock()
            mock_server.wait_for_termination = AsyncMock(side_effect=asyncio.CancelledError())
            mock_server.stop = AsyncMock()
            mock_grpc.aio.server.return_value = mock_server

            mock_health_servicer = MagicMock()
            mock_health_module.HealthServicer.return_value = mock_health_servicer

            mock_health_pb2.HealthCheckResponse.SERVING = 1

            # Run serve (will be cancelled immediately)
            try:
                await main_module.serve()
            except asyncio.CancelledError:
                pass

            # Verify clients were initialized
            mock_redis.connect.assert_called_once()
            mock_user.connect.assert_called_once()

            # Verify gRPC server was started
            mock_grpc.aio.server.assert_called_once()
            mock_server.start.assert_called_once()

            # Verify health check was set up
            mock_health_servicer.set.assert_called()

    def test_create_jwt_handler_requires_secret_for_hs256(self) -> None:
        """Should raise error when JWT_SECRET_KEY is not set for HS256."""
        from unittest.mock import patch

        import src.main as main_module

        with patch.object(main_module, "config") as mock_config:
            mock_config.jwt_algorithm = "HS256"
            mock_config.jwt_secret_key = ""
            mock_config.access_token_expire_minutes = 15
            mock_config.refresh_token_expire_days = 7

            with pytest.raises(ValueError, match="JWT_SECRET_KEY is required"):
                main_module.create_jwt_handler()

    def test_create_jwt_handler_requires_keys_for_rs256(self) -> None:
        """Should raise error when key paths are not set for RS256."""
        from unittest.mock import patch

        import src.main as main_module

        with patch.object(main_module, "config") as mock_config:
            mock_config.jwt_algorithm = "RS256"
            mock_config.jwt_private_key_path = ""
            mock_config.jwt_public_key_path = ""
            mock_config.access_token_expire_minutes = 15
            mock_config.refresh_token_expire_days = 7

            with pytest.raises(ValueError, match="RS256 algorithm requires"):
                main_module.create_jwt_handler()
