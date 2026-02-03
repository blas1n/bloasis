"""Classification Service gRPC client.

Provides typed client for communicating with Classification Service.
"""

import logging

import grpc

from shared.generated import classification_pb2, classification_pb2_grpc

from ..config import config
from ..models import CandidateSymbol

logger = logging.getLogger(__name__)


class ClassificationClient:
    """gRPC client for Classification Service."""

    def __init__(self, host: str | None = None, port: int | None = None):
        """Initialize Classification client.

        Args:
            host: Service host (default from config)
            port: Service port (default from config)
        """
        self.host = host or config.classification_host
        self.port = port or config.classification_port
        self.address = f"{self.host}:{self.port}"

        self.channel: grpc.aio.Channel | None = None
        self.stub: classification_pb2_grpc.ClassificationServiceStub | None = None

    async def connect(self) -> None:
        """Establish gRPC connection to Classification Service."""
        if self.channel:
            logger.warning("Classification client already connected")
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
        self.stub = classification_pb2_grpc.ClassificationServiceStub(self.channel)
        logger.info(f"Connected to Classification Service at {self.address}")

    async def get_candidate_symbols(
        self, regime: str, max_candidates: int = 50, force_refresh: bool = False
    ) -> tuple[list[CandidateSymbol], list[str], list[str]]:
        """Get candidate symbols from Classification Service.

        Args:
            regime: Market regime
            max_candidates: Maximum number of candidates to return
            force_refresh: If True, bypass cache and force fresh analysis

        Returns:
            Tuple of (candidates, selected_sectors, top_themes)

        Raises:
            grpc.RpcError: On gRPC communication errors
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = classification_pb2.GetCandidateSymbolsRequest(
                regime=regime, max_candidates=max_candidates, force_refresh=force_refresh
            )
            response = await self.stub.GetCandidateSymbols(request, timeout=60.0)

            # Convert proto to internal models
            candidates = [
                CandidateSymbol(
                    symbol=c.symbol,
                    sector=c.sector,
                    theme=c.theme,
                    preliminary_score=c.preliminary_score,
                )
                for c in response.candidates
            ]

            logger.info(
                f"Retrieved {len(candidates)} candidates from "
                f"{len(response.selected_sectors)} sectors"
            )
            return candidates, list(response.selected_sectors), list(response.top_themes)

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling Classification Service: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(
                    f"Classification Service unavailable at {self.address}"
                ) from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Classification Service request timed out") from e

            # Re-raise other errors
            raise

    async def get_sector_analysis(
        self, regime: str, force_refresh: bool = False
    ) -> classification_pb2.GetSectorAnalysisResponse:
        """Get sector analysis from Classification Service.

        Args:
            regime: Market regime
            force_refresh: If True, bypass cache and force fresh analysis

        Returns:
            GetSectorAnalysisResponse with sector scores

        Raises:
            grpc.RpcError: On gRPC communication errors
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = classification_pb2.GetSectorAnalysisRequest(
                regime=regime, force_refresh=force_refresh
            )
            response = await self.stub.GetSectorAnalysis(request, timeout=60.0)

            logger.info(f"Retrieved sector analysis for regime: {regime}")
            return response

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling Classification Service: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(
                    f"Classification Service unavailable at {self.address}"
                ) from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Classification Service request timed out") from e

            raise

    async def get_thematic_analysis(
        self, sectors: list[str], regime: str, force_refresh: bool = False
    ) -> classification_pb2.GetThematicAnalysisResponse:
        """Get thematic analysis from Classification Service.

        Args:
            sectors: Selected sectors
            regime: Market regime
            force_refresh: If True, bypass cache and force fresh analysis

        Returns:
            GetThematicAnalysisResponse with theme scores

        Raises:
            grpc.RpcError: On gRPC communication errors
        """
        if not self.stub:
            await self.connect()

        assert self.stub is not None, "stub should be initialized after connect()"

        try:
            request = classification_pb2.GetThematicAnalysisRequest(
                sectors=sectors, regime=regime, force_refresh=force_refresh
            )
            response = await self.stub.GetThematicAnalysis(request, timeout=60.0)

            logger.info(f"Retrieved thematic analysis for {len(sectors)} sectors")
            return response

        except grpc.RpcError as e:
            logger.error(f"gRPC error calling Classification Service: {e.code()} - {e.details()}")

            if e.code() == grpc.StatusCode.UNAVAILABLE:
                raise ConnectionError(
                    f"Classification Service unavailable at {self.address}"
                ) from e
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError("Classification Service request timed out") from e

            raise

    async def close(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Classification client closed")
