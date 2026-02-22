"""Executor Service gRPC client for User Service.

Used by GetBrokerStatus to verify Alpaca connection.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

import grpc
from shared.generated import executor_pb2, executor_pb2_grpc

from ..config import config

logger = logging.getLogger(__name__)


@dataclass
class AccountData:
    """Account data from Alpaca via Executor."""

    cash: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    equity: Decimal


class ExecutorClient:
    """gRPC client for Executor Service."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        """Initialize Executor client.

        Args:
            host: Service host (default from config).
            port: Service port (default from config).
        """
        self.host = host or config.executor_host
        self.port = port or config.executor_port
        self.address = f"{self.host}:{self.port}"
        self.channel: grpc.aio.Channel | None = None
        self.stub: executor_pb2_grpc.ExecutorServiceStub | None = None

    async def connect(self) -> None:
        """Establish gRPC connection to Executor Service."""
        if self.channel:
            return

        self.channel = grpc.aio.insecure_channel(
            self.address,
            options=[
                ("grpc.keepalive_time_ms", 10000),
                ("grpc.keepalive_timeout_ms", 5000),
            ],
        )
        self.stub = executor_pb2_grpc.ExecutorServiceStub(self.channel)
        logger.info(f"Connected to Executor Service at {self.address}")

    async def get_account(self, user_id: str = "") -> AccountData:
        """Get account info from Alpaca via Executor.

        Args:
            user_id: User identifier.

        Returns:
            AccountData with balance details.
        """
        if not self.stub:
            await self.connect()
        assert self.stub is not None

        request = executor_pb2.GetAccountRequest(user_id=user_id)
        response = await self.stub.GetAccount(request, timeout=10.0)
        return AccountData(
            cash=Decimal(str(response.cash)),
            buying_power=Decimal(str(response.buying_power)),
            portfolio_value=Decimal(str(response.portfolio_value)),
            equity=Decimal(str(response.equity)),
        )

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Executor client closed")
