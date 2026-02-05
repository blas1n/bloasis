"""Market Data Service gRPC client."""

import logging

import grpc
from shared.generated import market_data_pb2, market_data_pb2_grpc

from ..config import config

logger = logging.getLogger(__name__)


class MarketDataClient:
    """gRPC client for Market Data Service."""

    def __init__(self, host: str | None = None, port: int | None = None):
        """Initialize Market Data client.

        Args:
            host: Service host (default from config)
            port: Service port (default from config)
        """
        self.host = host or config.market_data_host
        self.port = port or config.market_data_port
        self.address = f"{self.host}:{self.port}"

        self.channel: grpc.aio.Channel | None = None
        self.stub: market_data_pb2_grpc.MarketDataServiceStub | None = None

    async def connect(self) -> None:
        """Establish gRPC connection to Market Data Service."""
        if self.channel:
            logger.warning("Market Data client already connected")
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
        self.stub = market_data_pb2_grpc.MarketDataServiceStub(self.channel)
        logger.info(f"Connected to Market Data Service at {self.address}")

    async def get_vix(self) -> float:
        """Get current VIX level.

        Returns:
            Current VIX value

        Raises:
            ConnectionError: On connection failure
            TimeoutError: On timeout
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = market_data_pb2.GetOHLCVRequest(symbol="^VIX", period="5d", interval="1d")
            response = await self.stub.GetOHLCV(request, timeout=10.0)

            if response.bars:
                return response.bars[-1].close
            return 20.0  # Default

        except grpc.RpcError as e:
            logger.error(f"gRPC error getting VIX: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(f"Market Data Service unavailable at {self.address}") from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Market Data Service request timed out") from e

            raise

    async def get_average_volume(self, symbol: str, days: int = 20) -> float:
        """Get average daily volume for a symbol.

        Args:
            symbol: Stock ticker symbol
            days: Number of days to average

        Returns:
            Average daily volume

        Raises:
            ConnectionError: On connection failure
            TimeoutError: On timeout
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = market_data_pb2.GetOHLCVRequest(
                symbol=symbol, period=f"{days}d", interval="1d"
            )
            response = await self.stub.GetOHLCV(request, timeout=10.0)

            if response.bars:
                total_volume = sum(bar.volume for bar in response.bars)
                return total_volume / len(response.bars)
            return 0.0

        except grpc.RpcError as e:
            logger.error(f"gRPC error getting volume for {symbol}: {e.code()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(f"Market Data Service unavailable at {self.address}") from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Market Data Service request timed out") from e

            raise

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Market Data client closed")
