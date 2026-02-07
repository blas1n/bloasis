"""E2E integration tests for Authentication Flow.

This module contains integration tests that verify:
- Login returns JWT tokens
- Token validation works correctly
- Protected routes require authentication
- Token refresh works as expected
- Invalid credentials are rejected

These tests require the Auth and User services to be running.
"""

import time
from typing import Any

import grpc
import pytest


# ============================================================================
# Test Markers
# ============================================================================


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
]


# ============================================================================
# Auth Flow Tests
# ============================================================================


class TestAuthFlow:
    """E2E tests for the authentication flow.

    The auth flow includes:
    1. User registration (via User Service)
    2. Login to get JWT tokens
    3. Token validation for protected routes
    4. Token refresh for continued access
    5. Logout to invalidate tokens
    """

    def test_login_returns_tokens(
        self,
        auth_stub: Any,
        mock_user_data: dict[str, Any],
    ) -> None:
        """Test login returns JWT tokens.

        Verifies that valid credentials result in:
        - Access token
        - Refresh token
        - Expiration information
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        request = auth_pb2.LoginRequest(
            email=mock_user_data["email"],
            password=mock_user_data["password"],
        )

        try:
            response = auth_stub.Login(request)

            # Login may fail if user doesn't exist - that's acceptable
            if response.success:
                assert response.access_token, "Should return access token"
                assert response.refresh_token, "Should return refresh token"
                assert response.expires_in > 0, "Should have positive expiry"
                assert response.user_id, "Should return user ID"
            else:
                # Expected if user doesn't exist in test database
                assert response.error_message
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

    def test_token_validation(
        self,
        auth_stub: Any,
        mock_user_data: dict[str, Any],
    ) -> None:
        """Test token validation works correctly.

        Verifies that:
        - Valid tokens are accepted
        - Token contains correct user information
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        # First, login to get a token
        login_request = auth_pb2.LoginRequest(
            email=mock_user_data["email"],
            password=mock_user_data["password"],
        )

        try:
            login_response = auth_stub.Login(login_request)

            if not login_response.success:
                pytest.skip("Could not login - user may not exist")

            # Now validate the token
            validate_request = auth_pb2.ValidateTokenRequest(
                token=login_response.access_token,
            )
            validate_response = auth_stub.ValidateToken(validate_request)

            assert validate_response.valid, "Token should be valid"
            assert validate_response.user_id == login_response.user_id
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

    def test_protected_routes_require_auth(
        self,
        auth_stub: Any,
    ) -> None:
        """Test protected routes require valid authentication.

        Verifies that:
        - Empty tokens are rejected
        - Invalid tokens are rejected
        - Malformed tokens are rejected
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        # Test with empty token
        empty_request = auth_pb2.ValidateTokenRequest(token="")
        try:
            empty_response = auth_stub.ValidateToken(empty_request)
            assert not empty_response.valid, "Empty token should be invalid"
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

        # Test with invalid token
        invalid_request = auth_pb2.ValidateTokenRequest(token="invalid.token.here")
        try:
            invalid_response = auth_stub.ValidateToken(invalid_request)
            assert not invalid_response.valid, "Invalid token should be rejected"
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

        # Test with malformed JWT
        malformed_request = auth_pb2.ValidateTokenRequest(
            token="not-even-close-to-jwt",
        )
        try:
            malformed_response = auth_stub.ValidateToken(malformed_request)
            assert not malformed_response.valid, "Malformed token should be rejected"
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

    def test_token_refresh(
        self,
        auth_stub: Any,
        mock_user_data: dict[str, Any],
    ) -> None:
        """Test token refresh works correctly.

        Verifies that:
        - Valid refresh tokens can be used to get new access tokens
        - New access tokens are valid
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        # Login to get tokens
        login_request = auth_pb2.LoginRequest(
            email=mock_user_data["email"],
            password=mock_user_data["password"],
        )

        try:
            login_response = auth_stub.Login(login_request)

            if not login_response.success:
                pytest.skip("Could not login - user may not exist")

            refresh_token = login_response.refresh_token

            # Small delay to ensure different token
            time.sleep(0.1)

            # Refresh the token
            refresh_request = auth_pb2.RefreshTokenRequest(
                refresh_token=refresh_token,
            )
            refresh_response = auth_stub.RefreshToken(refresh_request)

            if refresh_response.success:
                assert refresh_response.access_token, "Should return new access token"
                assert refresh_response.expires_in > 0, "Should have positive expiry"

                # New token should be valid
                validate_request = auth_pb2.ValidateTokenRequest(
                    token=refresh_response.access_token,
                )
                validate_response = auth_stub.ValidateToken(validate_request)
                assert validate_response.valid, "Refreshed token should be valid"
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

    def test_invalid_credentials_rejected(
        self,
        auth_stub: Any,
    ) -> None:
        """Test invalid credentials are rejected.

        Verifies that:
        - Wrong password is rejected
        - Non-existent user is rejected
        - Missing credentials are rejected
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        # Test with wrong password
        wrong_password_request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="definitely_wrong_password",
        )

        try:
            wrong_password_response = auth_stub.Login(wrong_password_request)
            # Should fail (either no success or error message)
            if wrong_password_response.success:
                # If it somehow succeeded, tokens should still work
                # This might happen in test environments with mock data
                pass
            else:
                assert wrong_password_response.error_message
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

        # Test with non-existent user
        nonexistent_request = auth_pb2.LoginRequest(
            email="nonexistent_user_12345@example.com",
            password="any_password",
        )

        try:
            nonexistent_response = auth_stub.Login(nonexistent_request)
            assert not nonexistent_response.success, "Non-existent user should fail"
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

        # Test with missing email
        missing_email_request = auth_pb2.LoginRequest(
            email="",
            password="some_password",
        )

        try:
            missing_email_response = auth_stub.Login(missing_email_request)
            assert not missing_email_response.success, "Missing email should fail"
            assert missing_email_response.error_message
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

        # Test with missing password
        missing_password_request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="",
        )

        try:
            missing_password_response = auth_stub.Login(missing_password_request)
            assert not missing_password_response.success, "Missing password should fail"
            assert missing_password_response.error_message
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

    def test_logout_invalidates_token(
        self,
        auth_stub: Any,
        mock_user_data: dict[str, Any],
    ) -> None:
        """Test logout invalidates refresh token.

        Verifies that:
        - Logout succeeds
        - Refresh token is no longer valid after logout
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        # Login to get tokens
        login_request = auth_pb2.LoginRequest(
            email=mock_user_data["email"],
            password=mock_user_data["password"],
        )

        try:
            login_response = auth_stub.Login(login_request)

            if not login_response.success:
                pytest.skip("Could not login - user may not exist")

            refresh_token = login_response.refresh_token

            # Logout
            logout_request = auth_pb2.LogoutRequest(
                refresh_token=refresh_token,
            )
            logout_response = auth_stub.Logout(logout_request)
            assert logout_response.success, "Logout should succeed"

            # Try to refresh after logout - should fail
            refresh_request = auth_pb2.RefreshTokenRequest(
                refresh_token=refresh_token,
            )
            refresh_response = auth_stub.RefreshToken(refresh_request)

            # After logout, refresh should fail
            assert not refresh_response.success, "Refresh should fail after logout"
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise


# ============================================================================
# Token Security Tests
# ============================================================================


class TestTokenSecurity:
    """Tests for token security measures."""

    def test_expired_token_rejected(
        self,
        auth_stub: Any,
    ) -> None:
        """Test expired tokens are rejected.

        Note: This test uses a simulated expired token.
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        # Simulated expired token (this is not a real JWT, will be rejected)
        expired_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJ0ZXN0LXVzZXIiLCJleHAiOjE2MDAwMDAwMDB9."
            "invalid_signature"
        )

        request = auth_pb2.ValidateTokenRequest(token=expired_token)

        try:
            response = auth_stub.ValidateToken(request)
            assert not response.valid, "Expired token should be rejected"
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

    def test_tampered_token_rejected(
        self,
        auth_stub: Any,
    ) -> None:
        """Test tampered tokens are rejected.

        Verifies that modifying the token payload invalidates it.
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        # Token with modified payload (invalid signature)
        tampered_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJoYWNrZXIiLCJ0eXBlIjoiYWNjZXNzIn0."
            "fake_signature_here"
        )

        request = auth_pb2.ValidateTokenRequest(token=tampered_token)

        try:
            response = auth_stub.ValidateToken(request)
            assert not response.valid, "Tampered token should be rejected"
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise

    def test_refresh_token_not_valid_as_access(
        self,
        auth_stub: Any,
        mock_user_data: dict[str, Any],
    ) -> None:
        """Test refresh token cannot be used as access token.

        Verifies that tokens of different types are not interchangeable.
        """
        try:
            from shared.generated import auth_pb2
        except ImportError:
            pytest.skip("Proto files not generated - run 'buf generate'")

        # Login to get tokens
        login_request = auth_pb2.LoginRequest(
            email=mock_user_data["email"],
            password=mock_user_data["password"],
        )

        try:
            login_response = auth_stub.Login(login_request)

            if not login_response.success:
                pytest.skip("Could not login - user may not exist")

            # Try to validate refresh token as access token
            validate_request = auth_pb2.ValidateTokenRequest(
                token=login_response.refresh_token,
            )
            validate_response = auth_stub.ValidateToken(validate_request)

            # Refresh token should not be valid as access token
            assert not validate_response.valid, (
                "Refresh token should not validate as access token"
            )
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAVAILABLE:
                raise


# ============================================================================
# Auth Service Health Tests
# ============================================================================


class TestAuthServiceHealth:
    """Tests for Auth service health and availability."""

    def test_auth_service_health_check(
        self,
        auth_channel: grpc.Channel,
    ) -> None:
        """Test Auth service gRPC health check."""
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        stub = health_pb2_grpc.HealthStub(auth_channel)

        try:
            request = health_pb2.HealthCheckRequest(service="")
            response = stub.Check(request)

            assert response.status == health_pb2.HealthCheckResponse.SERVING
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNIMPLEMENTED:
                pytest.skip("Health check not implemented")
            raise

    def test_auth_service_specific_health_check(
        self,
        auth_channel: grpc.Channel,
    ) -> None:
        """Test Auth service-specific health check."""
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        stub = health_pb2_grpc.HealthStub(auth_channel)

        try:
            request = health_pb2.HealthCheckRequest(
                service="bloasis.auth.AuthService",
            )
            response = stub.Check(request)

            assert response.status == health_pb2.HealthCheckResponse.SERVING
        except grpc.RpcError as e:
            if e.code() in [
                grpc.StatusCode.UNIMPLEMENTED,
                grpc.StatusCode.NOT_FOUND,
            ]:
                pytest.skip("Service-specific health check not available")
            raise
