"""User Service gRPC client for Executor Service.

Used to fetch broker credentials stored in User Service DB.
"""

import logging
from dataclasses import dataclass

import grpc
from shared.generated import user_pb2, user_pb2_grpc

from ..config import config

logger = logging.getLogger(__name__)


@dataclass
class BrokerConfig:
    """Broker configuration from User Service."""

    alpaca_api_key: str
    alpaca_secret_key: str
    paper: bool
    configured: bool


class UserClient:
    """gRPC client for User Service."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        """Initialize User client.

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
            return

        self.channel = grpc.aio.insecure_channel(
            self.address,
            options=[
                ("grpc.keepalive_time_ms", 10000),
                ("grpc.keepalive_timeout_ms", 5000),
            ],
        )
        self.stub = user_pb2_grpc.UserServiceStub(self.channel)
        logger.info(f"Connected to User Service at {self.address}")

    async def get_broker_config(self) -> BrokerConfig:
        """Get broker credentials from User Service.

        Returns:
            BrokerConfig with API keys and paper trading flag.
        """
        if not self.stub:
            await self.connect()
        if not self.stub:
            raise RuntimeError("Failed to connect to User Service")

        try:
            request = user_pb2.GetBrokerConfigRequest()
            response = await self.stub.GetBrokerConfig(request, timeout=10.0)
            return BrokerConfig(
                alpaca_api_key=response.alpaca_api_key,
                alpaca_secret_key=response.alpaca_secret_key,
                paper=response.paper,
                configured=response.configured,
            )
        except grpc.RpcError as e:
            logger.error(f"Failed to get broker config: {e.code()} - {e.details()}")
            raise

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("User client closed")
