"""Risk Committee Service gRPC client for Executor Service.

Used to request order approval before execution.
"""

import logging
from dataclasses import dataclass

import grpc
from shared.generated import risk_committee_pb2, risk_committee_pb2_grpc
from shared.utils.resilience import grpc_retry

from ..config import config

logger = logging.getLogger(__name__)


@dataclass
class RiskApproval:
    """Risk evaluation result from Risk Committee."""

    approved: bool
    decision: str  # "approve", "reject", "adjust"
    risk_score: float
    risk_approval_id: str
    reasoning: str
    warnings: list[str]


class RiskCommitteeClient:
    """gRPC client for Risk Committee Service."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        """Initialize Risk Committee client.

        Args:
            host: Service host (default from config).
            port: Service port (default from config).
        """
        self.host = host or config.risk_committee_host
        self.port = port or config.risk_committee_port
        self.address = f"{self.host}:{self.port}"
        self.channel: grpc.aio.Channel | None = None
        self.stub: risk_committee_pb2_grpc.RiskCommitteeServiceStub | None = None

    async def connect(self) -> None:
        """Establish gRPC connection to Risk Committee Service."""
        if self.channel:
            return

        self.channel = grpc.aio.insecure_channel(
            self.address,
            options=[
                ("grpc.keepalive_time_ms", 10000),
                ("grpc.keepalive_timeout_ms", 5000),
            ],
        )
        self.stub = risk_committee_pb2_grpc.RiskCommitteeServiceStub(self.channel)
        logger.info(f"Connected to Risk Committee Service at {self.address}")

    @grpc_retry
    async def evaluate_order(
        self,
        user_id: str,
        symbol: str,
        action: str,
        size: float,
        price: float,
        order_type: str = "market",
    ) -> RiskApproval:
        """Evaluate an order through Risk Committee.

        Args:
            user_id: User identifier.
            symbol: Stock ticker symbol.
            action: "buy" or "sell".
            size: Number of shares.
            price: Price per share.
            order_type: Order type ("market", "limit", "stop").

        Returns:
            RiskApproval with decision and risk score.
        """
        if not self.stub:
            await self.connect()
        if not self.stub:
            raise RuntimeError("Failed to connect to Risk Committee Service")

        try:
            request = risk_committee_pb2.EvaluateOrderRequest(
                user_id=user_id,
                symbol=symbol,
                action=action,
                size=size,
                price=price,
                order_type=order_type,
            )
            response = await self.stub.EvaluateOrder(request, timeout=30.0)
            return RiskApproval(
                approved=response.approved,
                decision=response.decision,
                risk_score=response.risk_score,
                risk_approval_id="",  # Will be set by caller after Redis storage
                reasoning=response.reasoning,
                warnings=list(response.warnings),
            )
        except grpc.RpcError as e:
            logger.error(f"Risk evaluation failed: {e.code()} - {e.details()}")
            raise

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Risk Committee client closed")
