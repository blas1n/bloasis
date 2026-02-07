"""Tests for User Service gRPC client.

Comprehensive tests covering:
- connect() method with channel and stub creation
- validate_credentials() success and error paths
- close() method with proper cleanup
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from src.clients.user_client import UserClient


class MockRpcError(grpc.RpcError, Exception):
    """Mock gRPC RpcError for testing error handling."""

    def __init__(self, status_code: grpc.StatusCode, details: str = "") -> None:
        """Initialize mock RPC error.

        Args:
            status_code: gRPC status code to return.
            details: Error details message.
        """
        super().__init__(details)
        self._code = status_code
        self._details = details

    def code(self) -> grpc.StatusCode:
        """Return the gRPC status code."""
        return self._code

    def details(self) -> str:
        """Return the error details."""
        return self._details


class TestUserClientInit:
    """Tests for UserClient initialization."""

    def test_init_with_default_values(self) -> None:
        """Test initialization uses config defaults."""
        with patch("src.clients.user_client.config") as mock_config:
            mock_config.user_service_host = "default-host"
            mock_config.user_service_port = 50061

            client = UserClient()

            assert client.host == "default-host"
            assert client.port == 50061
            assert client.address == "default-host:50061"
            assert client.channel is None
            assert client.stub is None

    def test_init_with_custom_values(self) -> None:
        """Test initialization with custom host and port."""
        client = UserClient(host="custom-host", port=9999)

        assert client.host == "custom-host"
        assert client.port == 9999
        assert client.address == "custom-host:9999"


class TestUserClientConnect:
    """Tests for UserClient.connect() method."""

    @pytest.fixture
    def mock_channel(self) -> MagicMock:
        """Create mock gRPC channel."""
        channel = MagicMock()
        channel.close = AsyncMock()
        return channel

    @pytest.fixture
    def mock_stub(self) -> MagicMock:
        """Create mock UserService stub."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_connect_creates_channel_and_stub(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test that connect() creates channel and stub."""
        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)
                await client.connect()

                mock_insecure.assert_called_once()
                # Verify channel options are passed
                call_args = mock_insecure.call_args
                assert call_args[0][0] == "localhost:50061"
                assert "options" in call_args[1] or len(call_args[0]) > 1

                mock_stub_class.assert_called_once_with(mock_channel)
                assert client.channel is mock_channel
                assert client.stub is mock_stub

    @pytest.mark.asyncio
    async def test_connect_already_connected_warns(
        self, mock_channel: MagicMock, mock_stub: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that connecting when already connected logs warning."""
        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)

                with caplog.at_level(logging.WARNING):
                    await client.connect()
                    await client.connect()  # Second call should warn

                assert "already connected" in caplog.text.lower()
                # insecure_channel should only be called once
                assert mock_insecure.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_logs_success(
        self, mock_channel: MagicMock, mock_stub: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that successful connection is logged."""
        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="testhost", port=12345)

                with caplog.at_level(logging.INFO):
                    await client.connect()

                assert "Connected to User Service" in caplog.text
                assert "testhost:12345" in caplog.text


class TestUserClientValidateCredentials:
    """Tests for UserClient.validate_credentials() method."""

    @pytest.fixture
    def mock_channel(self) -> MagicMock:
        """Create mock gRPC channel."""
        channel = MagicMock()
        channel.close = AsyncMock()
        return channel

    @pytest.fixture
    def mock_stub(self) -> MagicMock:
        """Create mock UserService stub."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_validate_credentials_success_valid(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test successful credential validation returns valid result."""
        mock_response = MagicMock()
        mock_response.valid = True
        mock_response.user_id = "user-123"
        mock_stub.ValidateCredentials = AsyncMock(return_value=mock_response)

        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)
                valid, user_id = await client.validate_credentials(
                    "test@example.com", "password123"
                )

                assert valid is True
                assert user_id == "user-123"

    @pytest.mark.asyncio
    async def test_validate_credentials_success_invalid(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test credential validation returns invalid result."""
        mock_response = MagicMock()
        mock_response.valid = False
        mock_response.user_id = ""
        mock_stub.ValidateCredentials = AsyncMock(return_value=mock_response)

        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)
                valid, user_id = await client.validate_credentials(
                    "wrong@example.com", "wrongpass"
                )

                assert valid is False
                assert user_id == ""

    @pytest.mark.asyncio
    async def test_validate_credentials_auto_connects(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test that validate_credentials auto-connects if not connected."""
        mock_response = MagicMock()
        mock_response.valid = True
        mock_response.user_id = "auto-user"
        mock_stub.ValidateCredentials = AsyncMock(return_value=mock_response)

        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)
                # Don't call connect() explicitly
                assert client.stub is None

                valid, user_id = await client.validate_credentials("test@example.com", "pass")

                # Should have auto-connected
                mock_insecure.assert_called_once()
                assert valid is True
                assert user_id == "auto-user"

    @pytest.mark.asyncio
    async def test_validate_credentials_unavailable_raises_connection_error(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test that UNAVAILABLE error raises ConnectionError."""
        mock_error = MockRpcError(grpc.StatusCode.UNAVAILABLE, "Service unavailable")
        mock_stub.ValidateCredentials = AsyncMock(side_effect=mock_error)

        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)

                with pytest.raises(ConnectionError) as exc_info:
                    await client.validate_credentials("test@example.com", "password")

                assert "User Service unavailable" in str(exc_info.value)
                assert "localhost:50061" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_credentials_timeout_raises_timeout_error(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test that DEADLINE_EXCEEDED error raises TimeoutError."""
        mock_error = MockRpcError(grpc.StatusCode.DEADLINE_EXCEEDED, "Deadline exceeded")
        mock_stub.ValidateCredentials = AsyncMock(side_effect=mock_error)

        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)

                with pytest.raises(TimeoutError) as exc_info:
                    await client.validate_credentials("test@example.com", "password")

                assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_validate_credentials_other_grpc_error_reraises(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test that other gRPC errors are re-raised."""
        mock_error = MockRpcError(grpc.StatusCode.INTERNAL, "Internal error")
        mock_stub.ValidateCredentials = AsyncMock(side_effect=mock_error)

        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)

                # Should re-raise the original grpc.RpcError
                with pytest.raises(grpc.RpcError):
                    await client.validate_credentials("test@example.com", "password")

    @pytest.mark.asyncio
    async def test_validate_credentials_logs_error_on_grpc_failure(
        self, mock_channel: MagicMock, mock_stub: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that gRPC errors are logged."""
        mock_error = MockRpcError(grpc.StatusCode.UNAVAILABLE, "Connection refused")
        mock_stub.ValidateCredentials = AsyncMock(side_effect=mock_error)

        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)

                with caplog.at_level(logging.ERROR):
                    with pytest.raises(ConnectionError):
                        await client.validate_credentials("test@example.com", "password")

                assert "gRPC error" in caplog.text


class TestUserClientClose:
    """Tests for UserClient.close() method."""

    @pytest.fixture
    def mock_channel(self) -> MagicMock:
        """Create mock gRPC channel."""
        channel = MagicMock()
        channel.close = AsyncMock()
        return channel

    @pytest.fixture
    def mock_stub(self) -> MagicMock:
        """Create mock UserService stub."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_close_closes_channel(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test that close() closes the channel and cleans up."""
        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)
                await client.connect()

                assert client.channel is not None
                assert client.stub is not None

                await client.close()

                mock_channel.close.assert_called_once()
                assert client.channel is None
                assert client.stub is None

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self) -> None:
        """Test that close() is safe when not connected."""
        client = UserClient(host="localhost", port=50061)

        # Should not raise any exception
        await client.close()

        assert client.channel is None
        assert client.stub is None

    @pytest.mark.asyncio
    async def test_close_logs_success(
        self, mock_channel: MagicMock, mock_stub: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that successful close is logged."""
        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)
                await client.connect()

                with caplog.at_level(logging.INFO):
                    await client.close()

                assert "User client closed" in caplog.text

    @pytest.mark.asyncio
    async def test_close_multiple_times_safe(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test that calling close() multiple times is safe."""
        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)
                await client.connect()

                await client.close()
                await client.close()  # Second close should be safe

                # Channel close should only be called once
                mock_channel.close.assert_called_once()


class TestUserClientIntegration:
    """Integration-style tests for UserClient lifecycle."""

    @pytest.fixture
    def mock_channel(self) -> MagicMock:
        """Create mock gRPC channel."""
        channel = MagicMock()
        channel.close = AsyncMock()
        return channel

    @pytest.fixture
    def mock_stub(self) -> MagicMock:
        """Create mock UserService stub."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_full_lifecycle(
        self, mock_channel: MagicMock, mock_stub: MagicMock
    ) -> None:
        """Test complete client lifecycle: connect -> validate -> close."""
        mock_response = MagicMock()
        mock_response.valid = True
        mock_response.user_id = "lifecycle-user"
        mock_stub.ValidateCredentials = AsyncMock(return_value=mock_response)

        with patch("src.clients.user_client.grpc.aio.insecure_channel") as mock_insecure:
            with patch(
                "src.clients.user_client.user_pb2_grpc.UserServiceStub"
            ) as mock_stub_class:
                mock_insecure.return_value = mock_channel
                mock_stub_class.return_value = mock_stub

                client = UserClient(host="localhost", port=50061)

                # Connect
                await client.connect()
                assert client.channel is not None

                # Validate credentials
                valid, user_id = await client.validate_credentials(
                    "test@example.com", "password"
                )
                assert valid is True
                assert user_id == "lifecycle-user"

                # Close
                await client.close()
                assert client.channel is None
                assert client.stub is None
