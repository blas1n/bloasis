"""Portfolio Service gRPC client."""

import logging
from decimal import Decimal
from typing import Any

import grpc
from shared.generated import portfolio_pb2, portfolio_pb2_grpc

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
        self.stub: portfolio_pb2_grpc.PortfolioServiceStub | None = None

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
        self.stub = portfolio_pb2_grpc.PortfolioServiceStub(self.channel)
        logger.info(f"Connected to Portfolio Service at {self.address}")

    async def get_positions(self, user_id: str) -> Portfolio:
        """Get user's portfolio positions.

        Args:
            user_id: User identifier

        Returns:
            Portfolio with positions

        Raises:
            ConnectionError: If Portfolio Service unavailable
            TimeoutError: If request times out
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = portfolio_pb2.GetPositionsRequest(user_id=user_id)
            response = await self.stub.GetPositions(request, timeout=10.0)

            logger.info(f"Retrieved {len(response.positions)} positions for user {user_id}")

            # Convert proto response to internal models
            positions = [
                PortfolioPosition(
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    market_value=self._money_to_float(pos.current_value),
                    sector=self._get_sector(pos.symbol),
                )
                for pos in response.positions
            ]

            # Calculate total value from positions
            total_value = sum(p.market_value for p in positions)

            return Portfolio(
                user_id=user_id,
                total_value=total_value,
                positions=positions,
            )

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling Portfolio Service: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(f"Portfolio Service unavailable at {self.address}") from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Portfolio Service request timed out") from e

            raise

    def _money_to_float(self, money: Any) -> float:
        """Convert Money proto to float.

        Args:
            money: Money proto message with string amount

        Returns:
            Float value of the amount
        """
        if money and money.amount:
            return float(Decimal(money.amount))
        return 0.0

    def _get_sector(self, symbol: str) -> str:
        """Get sector for symbol.

        TODO: In Phase 2, call MarketDataService.GetStockInfo for real sector.
        For now, return 'Unknown' - concentration_risk.py has sector mapping.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Sector name or 'Unknown'
        """
        return "Unknown"

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Portfolio client closed")
