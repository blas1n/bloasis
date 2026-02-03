"""Market Data Service gRPC client.

Provides typed client for communicating with Market Data Service.
"""

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

    async def get_ohlcv(self, symbol: str, period: str = "3mo", interval: str = "1d") -> list[dict]:
        """Get OHLCV data for a symbol.

        Args:
            symbol: Stock ticker symbol
            period: Data period (e.g., "1d", "5d", "1mo", "3mo", "1y")
            interval: Data interval (e.g., "1m", "5m", "1h", "1d")

        Returns:
            List of OHLCV bars as dictionaries

        Raises:
            grpc.RpcError: On gRPC communication errors
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = market_data_pb2.GetOHLCVRequest(
                symbol=symbol, period=period, interval=interval
            )
            response = await self.stub.GetOHLCV(request, timeout=30.0)

            # Convert proto bars to dicts
            ohlcv_bars = [
                {
                    "timestamp": bar.timestamp,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "adj_close": bar.adj_close if bar.HasField("adj_close") else None,
                }
                for bar in response.bars
            ]

            logger.info(f"Retrieved {len(ohlcv_bars)} OHLCV bars for {symbol}")
            return ohlcv_bars

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling Market Data Service: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(f"Market Data Service unavailable at {self.address}") from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Market Data Service request timed out") from e

            # Re-raise other errors
            raise

    async def get_stock_info(self, symbol: str) -> market_data_pb2.GetStockInfoResponse:
        """Get stock information/metadata.

        Args:
            symbol: Stock ticker symbol

        Returns:
            GetStockInfoResponse with stock metadata

        Raises:
            grpc.RpcError: On gRPC communication errors
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = market_data_pb2.GetStockInfoRequest(symbol=symbol)
            response = await self.stub.GetStockInfo(request, timeout=30.0)

            logger.info(f"Retrieved stock info for {symbol}")
            return response

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling Market Data Service: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(f"Market Data Service unavailable at {self.address}") from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Market Data Service request timed out") from e

            raise

    async def get_batch_ohlcv(
        self, symbols: list[str], period: str = "3mo", interval: str = "1d"
    ) -> dict[str, list[dict]]:
        """Get OHLCV data for multiple symbols.

        Args:
            symbols: List of stock ticker symbols
            period: Data period
            interval: Data interval

        Returns:
            Dict mapping symbol to list of OHLCV bars

        Raises:
            grpc.RpcError: On gRPC communication errors
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = market_data_pb2.GetBatchOHLCVRequest(
                symbols=symbols, period=period, interval=interval
            )
            response = await self.stub.GetBatchOHLCV(request, timeout=60.0)

            # Convert proto response to dict of lists
            result = {}
            for symbol, ohlcv_response in response.data.items():
                result[symbol] = [
                    {
                        "timestamp": bar.timestamp,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        "adj_close": bar.adj_close if bar.HasField("adj_close") else None,
                    }
                    for bar in ohlcv_response.bars
                ]

            logger.info(f"Retrieved OHLCV data for {len(result)} symbols")
            return result

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling Market Data Service: {e.code()} - {e.details()}")

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
