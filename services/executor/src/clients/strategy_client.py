"""Strategy Service gRPC client for Executor Service.

Used to trigger AI analysis when auto-trading is started.
"""

import logging

import grpc
from shared.generated import strategy_pb2, strategy_pb2_grpc
from shared.utils.resilience import grpc_retry

from ..config import config

logger = logging.getLogger(__name__)


class StrategyClient:
    """gRPC client for Strategy Service."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        """Initialize Strategy client.

        Args:
            host: Service host (default from config).
            port: Service port (default from config).
        """
        self.host = host or config.strategy_service_host
        self.port = port or config.strategy_service_port
        self.address = f"{self.host}:{self.port}"
        self.channel: grpc.aio.Channel | None = None
        self.stub: strategy_pb2_grpc.StrategyServiceStub | None = None

    async def connect(self) -> None:
        """Establish gRPC connection to Strategy Service."""
        if self.channel:
            return

        self.channel = grpc.aio.insecure_channel(
            self.address,
            options=[
                ("grpc.keepalive_time_ms", 300000),
                ("grpc.keepalive_timeout_ms", 20000),
            ],
        )
        self.stub = strategy_pb2_grpc.StrategyServiceStub(self.channel)
        logger.info(f"Connected to Strategy Service at {self.address}")

    @grpc_retry
    async def run_ai_analysis(self, user_id: str) -> strategy_pb2.RunAIAnalysisResponse:
        """Trigger AI analysis for a user.

        Executes the 5-Layer AI Flow and publishes signals to Redpanda.

        Args:
            user_id: User identifier.

        Returns:
            RunAIAnalysisResponse with analysis results and signal count.
        """
        if not self.stub:
            await self.connect()
        if not self.stub:
            raise RuntimeError("Failed to connect to Strategy Service")

        try:
            request = strategy_pb2.RunAIAnalysisRequest(user_id=user_id)
            response = await self.stub.RunAIAnalysis(request, timeout=600.0)
            return response
        except grpc.RpcError as e:
            logger.error(f"AI analysis trigger failed: {e.code()} - {e.details()}")
            raise

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Strategy client closed")
