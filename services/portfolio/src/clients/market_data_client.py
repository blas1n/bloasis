"""Market Data Service gRPC client for Portfolio Service."""

import logging
from decimal import Decimal

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

    async def get_current_price(self, symbol: str) -> Decimal:
        """Get current price for a symbol.

        Uses the GetOHLCV RPC with period="1d" and interval="1m" to fetch
        the most recent minute bar, extracting the close price as current price.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price as Decimal, or Decimal("0") if unavailable
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = market_data_pb2.GetOHLCVRequest(
                symbol=symbol, period="1d", interval="1m"
            )
            response = await self.stub.GetOHLCV(request, timeout=10.0)

            if response.bars:
                # Return the close price of the most recent bar
                return Decimal(str(response.bars[-1].close))
            logger.warning(f"No price data available for {symbol}")
            return Decimal("0")

        except grpc.RpcError as e:
            logger.warning(
                f"Failed to get price for {symbol}: {e.code()} - {e.details()}"
            )
            return Decimal("0")

    async def get_previous_close(self, symbol: str) -> Decimal | None:
        """Get previous day's closing price.

        Uses the GetOHLCV RPC with period="5d" and interval="1d" to fetch
        daily bars, extracting the second-to-last bar's close as yesterday's close.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Previous day's close as Decimal, or None if unavailable
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = market_data_pb2.GetOHLCVRequest(
                symbol=symbol, period="5d", interval="1d"
            )
            response = await self.stub.GetOHLCV(request, timeout=10.0)

            if len(response.bars) >= 2:
                # Return the close of the second-to-last bar (yesterday)
                return Decimal(str(response.bars[-2].close))
            logger.warning(f"Insufficient data for previous close of {symbol}")
            return None

        except grpc.RpcError as e:
            logger.warning(
                f"Failed to get previous close for {symbol}: {e.code()} - {e.details()}"
            )
            return None

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Market Data client closed")
