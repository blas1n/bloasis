"""Executor Service gRPC client for Portfolio Service.

Used by SyncWithAlpaca to fetch positions and account data from Alpaca
through the Executor Service (MSA boundary compliance).
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

import grpc
from shared.generated import executor_pb2, executor_pb2_grpc

from ..config import config

logger = logging.getLogger(__name__)


@dataclass
class AlpacaPositionData:
    """Position data from Alpaca via Executor."""

    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    side: str


@dataclass
class AlpacaAccountData:
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

    async def get_positions(self, user_id: str) -> list[AlpacaPositionData]:
        """Get positions from Alpaca via Executor.

        Args:
            user_id: User identifier.

        Returns:
            List of positions from Alpaca.
        """
        if not self.stub:
            await self.connect()
        assert self.stub is not None

        try:
            request = executor_pb2.GetPositionsRequest(user_id=user_id)
            response = await self.stub.GetPositions(request, timeout=30.0)
            return [
                AlpacaPositionData(
                    symbol=p.symbol,
                    qty=Decimal(str(p.qty)),
                    avg_entry_price=Decimal(str(p.avg_entry_price)),
                    current_price=Decimal(str(p.current_price)),
                    market_value=Decimal(str(p.market_value)),
                    unrealized_pl=Decimal(str(p.unrealized_pl)),
                    side=p.side,
                )
                for p in response.positions
            ]
        except grpc.RpcError as e:
            logger.error(f"Failed to get positions: {e.code()} - {e.details()}")
            raise

    async def get_account(self, user_id: str) -> AlpacaAccountData:
        """Get account info from Alpaca via Executor.

        Args:
            user_id: User identifier.

        Returns:
            Account data from Alpaca.
        """
        if not self.stub:
            await self.connect()
        assert self.stub is not None

        try:
            request = executor_pb2.GetAccountRequest(user_id=user_id)
            response = await self.stub.GetAccount(request, timeout=10.0)
            return AlpacaAccountData(
                cash=Decimal(str(response.cash)),
                buying_power=Decimal(str(response.buying_power)),
                portfolio_value=Decimal(str(response.portfolio_value)),
                equity=Decimal(str(response.equity)),
            )
        except grpc.RpcError as e:
            logger.error(f"Failed to get account: {e.code()} - {e.details()}")
            raise

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Executor client closed")
