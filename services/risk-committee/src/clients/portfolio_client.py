"""Portfolio Service gRPC client."""

import logging

import grpc

from ..config import config
from ..models import Portfolio, PortfolioPosition

logger = logging.getLogger(__name__)


class PortfolioClient:
    """gRPC client for Portfolio Service."""

    def __init__(self, host: str | None = None, port: int | None = None):
        """Initialize Portfolio client.

        Args:
            host: Service host (default from config)
            port: Service port (default from config)
        """
        self.host = host or config.portfolio_host
        self.port = port or config.portfolio_port
        self.address = f"{self.host}:{self.port}"

        self.channel: grpc.aio.Channel | None = None
        self.stub = None

    async def connect(self) -> None:
        """Establish gRPC connection to Portfolio Service."""
        if self.channel:
            logger.warning("Portfolio client already connected")
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
        # In production, would initialize stub from generated proto
        # self.stub = portfolio_pb2_grpc.PortfolioServiceStub(self.channel)
        logger.info(f"Connected to Portfolio Service at {self.address}")

    async def get_positions(self, user_id: str) -> Portfolio:
        """Get user's portfolio positions.

        Args:
            user_id: User identifier

        Returns:
            Portfolio with positions

        Raises:
            ConnectionError: On connection failure
            TimeoutError: On timeout
        """
        # For now, return mock data since Portfolio Service proto is not yet defined
        # In production, would call gRPC:
        # request = portfolio_pb2.GetPositionsRequest(user_id=user_id)
        # response = await self.stub.GetPositions(request, timeout=10.0)

        logger.info(f"Getting positions for user: {user_id}")

        # Return mock portfolio for development
        return Portfolio(
            user_id=user_id,
            total_value=100000.0,
            positions=[
                PortfolioPosition(
                    symbol="AAPL",
                    quantity=50,
                    market_value=8750.0,
                    sector="Technology",
                ),
                PortfolioPosition(
                    symbol="GOOGL",
                    quantity=20,
                    market_value=2800.0,
                    sector="Technology",
                ),
            ],
        )

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Portfolio client closed")
