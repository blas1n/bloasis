"""Market Regime Service gRPC client.

Provides typed client for communicating with Market Regime Service.
"""

import logging

import grpc

from shared.generated import market_regime_pb2, market_regime_pb2_grpc

from ..config import config

logger = logging.getLogger(__name__)


class MarketRegimeClient:
    """gRPC client for Market Regime Service."""

    def __init__(self, host: str | None = None, port: int | None = None):
        """Initialize Market Regime client.

        Args:
            host: Service host (default from config)
            port: Service port (default from config)
        """
        self.host = host or config.market_regime_host
        self.port = port or config.market_regime_port
        self.address = f"{self.host}:{self.port}"

        self.channel: grpc.aio.Channel | None = None
        self.stub: market_regime_pb2_grpc.MarketRegimeServiceStub | None = None

    async def connect(self) -> None:
        """Establish gRPC connection to Market Regime Service."""
        if self.channel:
            logger.warning("Market Regime client already connected")
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
        self.stub = market_regime_pb2_grpc.MarketRegimeServiceStub(self.channel)
        logger.info(f"Connected to Market Regime Service at {self.address}")

    async def get_current_regime(
        self, force_refresh: bool = False
    ) -> market_regime_pb2.GetCurrentRegimeResponse:
        """Get current market regime.

        Args:
            force_refresh: If True, bypass cache and force fresh analysis

        Returns:
            GetCurrentRegimeResponse with regime, confidence, timestamp

        Raises:
            grpc.RpcError: On gRPC communication errors
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=force_refresh)
            response = await self.stub.GetCurrentRegime(request, timeout=30.0)

            logger.info(
                f"Retrieved market regime: {response.regime} "
                f"(confidence: {response.confidence:.2f})"
            )
            return response

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling Market Regime Service: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(f"Market Regime Service unavailable at {self.address}") from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Market Regime Service request timed out") from e

            # Re-raise other errors
            raise

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Market Regime client closed")
