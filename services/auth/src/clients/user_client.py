"""User Service gRPC client.

Provides typed client for communicating with User Service.
Used to validate user credentials during login.
"""

import logging

import grpc
from shared.generated import user_pb2, user_pb2_grpc

from ..config import config

logger = logging.getLogger(__name__)


class UserClient:
    """gRPC client for User Service."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        """Initialize User Service client.

        Args:
            host: Service host (default from config).
            port: Service port (default from config).
        """
        self.host = host or config.user_service_host
        self.port = port or config.user_service_port
        self.address = f"{self.host}:{self.port}"

        self.channel: grpc.aio.Channel | None = None
        self.stub: user_pb2_grpc.UserServiceStub | None = None

    async def connect(self) -> None:
        """Establish gRPC connection to User Service."""
        if self.channel:
            logger.warning("User client already connected")
            return

        self.channel = grpc.aio.insecure_channel(
            self.address,
            options=[
                ("grpc.max_send_message_length", 50 * 1024 * 1024),
                ("grpc.max_receive_message_length", 50 * 1024 * 1024),
                ("grpc.keepalive_time_ms", 10000),
                ("grpc.keepalive_timeout_ms", 5000),
            ],
        )
        self.stub = user_pb2_grpc.UserServiceStub(self.channel)
        logger.info(f"Connected to User Service at {self.address}")

    async def validate_credentials(self, email: str, password: str) -> tuple[bool, str]:
        """Validate user credentials via User Service.

        Args:
            email: User's email address.
            password: User's password (never logged).

        Returns:
            Tuple of (is_valid, user_id). user_id is empty string if invalid.

        Raises:
            ConnectionError: If User Service is unavailable.
            TimeoutError: If request times out.
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = user_pb2.ValidateCredentialsRequest(
                email=email,
                password=password,
            )
            response = await self.stub.ValidateCredentials(request, timeout=10.0)

            logger.debug(f"Credential validation result for email: valid={response.valid}")
            return (response.valid, response.user_id)

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling User Service: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(f"User Service unavailable at {self.address}") from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("User Service request timed out") from e

            # Re-raise other errors
            raise

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("User client closed")
