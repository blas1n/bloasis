"""Classification Service - Core Business Logic.

Implements Stock Selection Pipeline Stage 1-2:
- Stage 1: Sector Filter (11 sectors → 3-7 sectors)
- Stage 2: Thematic Filter (theme ranking within selected sectors)
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

import grpc
from shared.ai_clients import ClaudeClient
from shared.generated import classification_pb2, classification_pb2_grpc

from .clients.market_regime_client import MarketRegimeClient
from .models import CandidateSymbol, SectorScore, ThemeScore
from .prompts import (
    format_sector_prompt,
    format_theme_prompt,
    get_sector_model_parameters,
    get_theme_model_parameters,
)
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
        analyst: ClaudeClient,
        regime_client: MarketRegimeClient,
        cache_manager: CacheManager,
        claude_model: str = "claude-haiku-4-5-20251001",
    ):
        """Initialize Classification Service.

        Args:
            analyst: Claude client for AI analysis
            regime_client: Market Regime Service gRPC client
            cache_manager: Redis cache manager
            claude_model: Claude model ID to use for analysis.
        """
        self.analyst = analyst
        self.claude_model = claude_model
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

        logger.info(f"Analyzing sectors for regime: {regime}")

        prompt = format_sector_prompt(regime=regime)
        params = get_sector_model_parameters()
        data = await self.analyst.analyze(
            prompt=prompt,
            model=self.claude_model,
            response_format="json",
            max_tokens=params.get("max_new_tokens", 1000),
        )
        sectors = self._parse_sector_response(data)

        # Sort by score descending
        sectors.sort(key=lambda s: s.score, reverse=True)

        # Cache result
        cached_at = datetime.now(timezone.utc).isoformat()
        await self.cache.set(
            cache_key,
            {
                "sectors": [s.model_dump() for s in sectors],
                "cached_at": cached_at,
            },
        )

        logger.info(
            f"Sector analysis completed: {sum(1 for s in sectors if s.selected)} selected"
        )
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

        logger.info(f"Analyzing themes for sectors: {sectors}")

        prompt = format_theme_prompt(sectors=sectors, regime=regime)
        params = get_theme_model_parameters()
        data = await self.analyst.analyze(
            prompt=prompt,
            model=self.claude_model,
            response_format="json",
            max_tokens=params.get("max_new_tokens", 1500),
        )
        themes = self._parse_theme_response(data)

        themes.sort(key=lambda t: t.score, reverse=True)

        cached_at = datetime.now(timezone.utc).isoformat()
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
        self,
        regime: Optional[str] = None,
        max_candidates: int = 50,
        force_refresh: bool = False,
    ) -> tuple[List[CandidateSymbol], List[str], List[str], str]:
        """Stage 1+2 Combined: Get candidate symbols."""
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
        themes, _ = await self.get_thematic_analysis(
            selected_sectors, regime, force_refresh
        )

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

    def _parse_sector_response(self, data: dict) -> List[SectorScore]:
        """Parse Claude's sector analysis response into SectorScore models."""
        return [
            SectorScore(
                sector=s["sector"],
                score=float(s["score"]),
                rationale=s.get("rationale", "AI analysis"),
                selected=s.get("selected", False),
            )
            for s in data.get("sectors", [])
            if "sector" in s and "score" in s
        ]

    def _parse_theme_response(self, data: dict) -> List[ThemeScore]:
        """Parse Claude's theme analysis response into ThemeScore models."""
        return [
            ThemeScore(
                theme=t["theme"],
                sector=t["sector"],
                score=float(t["score"]),
                rationale=t.get("rationale", "AI analysis"),
                representative_symbols=t.get("representative_symbols", []),
            )
            for t in data.get("themes", [])
            if "theme" in t and "sector" in t and "score" in t
        ]


class ClassificationServicer(classification_pb2_grpc.ClassificationServiceServicer):
    """gRPC servicer for Classification Service."""

    def __init__(self, service: ClassificationService):
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

            sectors, cached_at = await self.service.get_sector_analysis(
                regime, force_refresh
            )

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

            themes, cached_at = await self.service.get_thematic_analysis(
                sectors, regime, force_refresh
            )

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
            regime = request.regime or None
            max_candidates = request.max_candidates or 50
            force_refresh = request.force_refresh

            logger.info(
                f"GetCandidateSymbols request: regime={regime}, "
                f"max_candidates={max_candidates}, force_refresh={force_refresh}"
            )

            (
                candidates,
                selected_sectors,
                top_themes,
                used_regime,
            ) = await self.service.get_candidate_symbols(
                regime, max_candidates, force_refresh
            )

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

        except ConnectionError:
            logger.error("Market Regime Service unavailable")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Market Regime Service unavailable")
            return classification_pb2.GetCandidateSymbolsResponse()

        except TimeoutError:
            logger.error("Market Regime Service timeout")
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details("Market Regime Service request timed out")
            return classification_pb2.GetCandidateSymbolsResponse()

        except Exception as e:
            logger.error(f"GetCandidateSymbols error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return classification_pb2.GetCandidateSymbolsResponse()
