"""Classification Service - Core Business Logic.

Implements Stock Selection Pipeline Stage 1-2:
- Stage 1: Sector Filter (11 sectors → 3-7 sectors)
- Stage 2: Thematic Filter (theme ranking within selected sectors)
"""

import logging
from datetime import datetime
from typing import List, Optional

import grpc
from shared.generated import classification_pb2, classification_pb2_grpc

from .clients.fingpt_client import FinGPTClientBase
from .clients.market_regime_client import MarketRegimeClient
from .models import CandidateSymbol, SectorScore, ThemeScore
from .utils.cache import (
    CacheManager,
    build_candidate_cache_key,
    build_sector_cache_key,
    build_theme_cache_key,
)

logger = logging.getLogger(__name__)


class ClassificationService:
    """Classification Service implementing Stock Selection Pipeline Stage 1-2."""

    def __init__(
        self,
        fingpt_client: FinGPTClientBase,
        regime_client: MarketRegimeClient,
        cache_manager: CacheManager,
    ):
        """Initialize Classification Service.

        Args:
            fingpt_client: FinGPT client for sector/theme analysis
            regime_client: Market Regime Service gRPC client
            cache_manager: Redis cache manager
        """
        self.fingpt = fingpt_client
        self.regime_client = regime_client
        self.cache = cache_manager

        logger.info("Classification Service initialized")

    async def get_sector_analysis(
        self, regime: str, force_refresh: bool = False
    ) -> tuple[List[SectorScore], str]:
        """Stage 1: Sector Filter.

        Filters 11 GICS sectors down to 3-7 sectors based on market regime.

        Args:
            regime: Market regime from Market Regime Service
            force_refresh: If True, bypass cache and force fresh analysis

        Returns:
            Tuple of (sector_scores, cached_at timestamp)
        """
        cache_key = build_sector_cache_key(regime)

        # Try cache first (unless force_refresh)
        if not force_refresh:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(f"Sector analysis cache hit for regime: {regime}")
                return (
                    [SectorScore(**s) for s in cached["sectors"]],
                    cached["cached_at"],
                )

        # Cache miss - analyze with FinGPT
        logger.info(f"Analyzing sectors for regime: {regime}")
        sectors = await self.fingpt.analyze_sectors(regime)

        # Sort by score descending
        sectors.sort(key=lambda s: s.score, reverse=True)

        # Cache result
        cached_at = datetime.utcnow().isoformat() + "Z"
        await self.cache.set(
            cache_key,
            {
                "sectors": [s.model_dump() for s in sectors],
                "cached_at": cached_at,
            },
        )

        logger.info(f"Sector analysis completed: {sum(1 for s in sectors if s.selected)} selected")
        return sectors, cached_at

    async def get_thematic_analysis(
        self, sectors: List[str], regime: str, force_refresh: bool = False
    ) -> tuple[List[ThemeScore], str]:
        """Stage 2: Thematic Filter.

        Ranks investment themes within selected sectors.

        Args:
            sectors: Selected sectors from Stage 1
            regime: Market regime for context
            force_refresh: If True, bypass cache and force fresh analysis

        Returns:
            Tuple of (theme_scores, cached_at timestamp)
        """
        cache_key = build_theme_cache_key(sectors, regime)

        # Try cache first (unless force_refresh)
        if not force_refresh:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(f"Thematic analysis cache hit for sectors: {sectors}")
                return (
                    [ThemeScore(**t) for t in cached["themes"]],
                    cached["cached_at"],
                )

        # Cache miss - analyze with FinGPT
        logger.info(f"Analyzing themes for sectors: {sectors}")
        themes = await self.fingpt.analyze_themes(sectors, regime)

        # Already sorted by score in FinGPT client
        themes.sort(key=lambda t: t.score, reverse=True)

        # Cache result
        cached_at = datetime.utcnow().isoformat() + "Z"
        await self.cache.set(
            cache_key,
            {
                "themes": [t.model_dump() for t in themes],
                "cached_at": cached_at,
            },
        )

        logger.info(f"Thematic analysis completed: {len(themes)} themes identified")
        return themes, cached_at

    async def get_candidate_symbols(
        self, regime: Optional[str] = None, max_candidates: int = 50, force_refresh: bool = False
    ) -> tuple[List[CandidateSymbol], List[str], List[str], str]:
        """Stage 1+2 Combined: Get candidate symbols.

        Combines sector filter and thematic analysis to produce candidate list.

        Args:
            regime: Market regime (fetched from Market Regime Service if None)
            max_candidates: Maximum number of candidates to return
            force_refresh: If True, bypass cache and force fresh analysis

        Returns:
            Tuple of (candidates, selected_sectors, top_themes, regime)
        """
        # Fetch current regime if not provided
        if not regime:
            regime_response = await self.regime_client.get_current_regime()
            regime = regime_response.regime
            logger.info(f"Fetched current regime: {regime}")

        cache_key = build_candidate_cache_key(regime)

        # Try cache first (unless force_refresh)
        if not force_refresh:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(f"Candidate symbols cache hit for regime: {regime}")
                return (
                    [CandidateSymbol(**c) for c in cached["candidates"]],
                    cached["selected_sectors"],
                    cached["top_themes"],
                    cached["regime"],
                )

        # Cache miss - run full pipeline
        logger.info(f"Running full pipeline for regime: {regime}")

        # Stage 1: Sector Filter
        sectors, _ = await self.get_sector_analysis(regime, force_refresh)
        selected_sectors = [s.sector for s in sectors if s.selected]

        if not selected_sectors:
            logger.warning(f"No sectors selected for regime {regime}, using top 3")
            selected_sectors = [s.sector for s in sectors[:3]]

        # Stage 2: Thematic Filter
        themes, _ = await self.get_thematic_analysis(selected_sectors, regime, force_refresh)

        # Extract candidates from top themes
        candidates = []
        top_themes = []

        for theme in themes[:10]:  # Top 10 themes
            top_themes.append(theme.theme)
            for symbol in theme.representative_symbols:
                if len(candidates) >= max_candidates:
                    break

                candidates.append(
                    CandidateSymbol(
                        symbol=symbol,
                        sector=theme.sector,
                        theme=theme.theme,
                        preliminary_score=theme.score,
                    )
                )

            if len(candidates) >= max_candidates:
                break

        # Sort by preliminary score descending
        candidates.sort(key=lambda c: c.preliminary_score, reverse=True)
        candidates = candidates[:max_candidates]

        # Cache result
        await self.cache.set(
            cache_key,
            {
                "candidates": [c.model_dump() for c in candidates],
                "selected_sectors": selected_sectors,
                "top_themes": top_themes,
                "regime": regime,
            },
        )

        logger.info(
            f"Pipeline completed: {len(candidates)} candidates from "
            f"{len(selected_sectors)} sectors, {len(top_themes)} themes"
        )
        return candidates, selected_sectors, top_themes, regime


class ClassificationServicer(classification_pb2_grpc.ClassificationServiceServicer):
    """gRPC servicer for Classification Service."""

    def __init__(self, service: ClassificationService):
        """Initialize servicer.

        Args:
            service: Classification service instance
        """
        self.service = service
        logger.info("Classification gRPC servicer initialized")

    async def GetSectorAnalysis(
        self,
        request: classification_pb2.GetSectorAnalysisRequest,
        context: grpc.aio.ServicerContext,
    ) -> classification_pb2.GetSectorAnalysisResponse:
        """Get sector analysis (Stage 1: Sector Filter)."""
        try:
            regime = request.regime
            force_refresh = request.force_refresh

            if not regime:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("regime field is required")
                return classification_pb2.GetSectorAnalysisResponse()

            logger.info(
                f"GetSectorAnalysis request: regime={regime}, force_refresh={force_refresh}"
            )

            # Call business logic
            sectors, cached_at = await self.service.get_sector_analysis(regime, force_refresh)

            # Convert to proto response
            sector_protos = [
                classification_pb2.SectorScore(
                    sector=s.sector,
                    score=s.score,
                    rationale=s.rationale,
                    selected=s.selected,
                )
                for s in sectors
            ]

            return classification_pb2.GetSectorAnalysisResponse(
                sectors=sector_protos,
                regime=regime,
                cached_at=cached_at,
            )

        except Exception as e:
            logger.error(f"GetSectorAnalysis error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return classification_pb2.GetSectorAnalysisResponse()

    async def GetThematicAnalysis(
        self,
        request: classification_pb2.GetThematicAnalysisRequest,
        context: grpc.aio.ServicerContext,
    ) -> classification_pb2.GetThematicAnalysisResponse:
        """Get thematic analysis (Stage 2: Thematic Filter)."""
        try:
            sectors = list(request.sectors)
            regime = request.regime
            force_refresh = request.force_refresh

            if not sectors:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("sectors field is required and must not be empty")
                return classification_pb2.GetThematicAnalysisResponse()

            if not regime:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("regime field is required")
                return classification_pb2.GetThematicAnalysisResponse()

            logger.info(
                f"GetThematicAnalysis request: sectors={sectors}, "
                f"regime={regime}, force_refresh={force_refresh}"
            )

            # Call business logic
            themes, cached_at = await self.service.get_thematic_analysis(
                sectors, regime, force_refresh
            )

            # Convert to proto response
            theme_protos = [
                classification_pb2.ThemeScore(
                    theme=t.theme,
                    sector=t.sector,
                    score=t.score,
                    rationale=t.rationale,
                    representative_symbols=t.representative_symbols,
                )
                for t in themes
            ]

            return classification_pb2.GetThematicAnalysisResponse(
                themes=theme_protos,
                cached_at=cached_at,
            )

        except Exception as e:
            logger.error(f"GetThematicAnalysis error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return classification_pb2.GetThematicAnalysisResponse()

    async def GetCandidateSymbols(
        self,
        request: classification_pb2.GetCandidateSymbolsRequest,
        context: grpc.aio.ServicerContext,
    ) -> classification_pb2.GetCandidateSymbolsResponse:
        """Get candidate symbols (Stage 1+2 combined)."""
        try:
            regime = request.regime or None  # Empty string -> None
            max_candidates = request.max_candidates or 50
            force_refresh = request.force_refresh

            logger.info(
                f"GetCandidateSymbols request: regime={regime}, "
                f"max_candidates={max_candidates}, force_refresh={force_refresh}"
            )

            # Call business logic
            (
                candidates,
                selected_sectors,
                top_themes,
                used_regime,
            ) = await self.service.get_candidate_symbols(regime, max_candidates, force_refresh)

            # Convert to proto response
            candidate_protos = [
                classification_pb2.CandidateSymbol(
                    symbol=c.symbol,
                    sector=c.sector,
                    theme=c.theme,
                    preliminary_score=c.preliminary_score,
                )
                for c in candidates
            ]

            return classification_pb2.GetCandidateSymbolsResponse(
                candidates=candidate_protos,
                selected_sectors=selected_sectors,
                top_themes=top_themes,
                regime=used_regime,
            )

        except ConnectionError as e:
            logger.error(f"Market Regime Service unavailable: {e}")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Market Regime Service unavailable")
            return classification_pb2.GetCandidateSymbolsResponse()

        except TimeoutError as e:
            logger.error(f"Market Regime Service timeout: {e}")
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details("Market Regime Service request timed out")
            return classification_pb2.GetCandidateSymbolsResponse()

        except Exception as e:
            logger.error(f"GetCandidateSymbols error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return classification_pb2.GetCandidateSymbolsResponse()
