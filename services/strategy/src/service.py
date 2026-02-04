"""Strategy Service - gRPC Servicer Implementation.

Implements Stock Selection Pipeline Stage 3:
- Stage 3: Factor Scoring (6 factors with risk profile-based weighting)
- User Preferences Management (risk profiles, sector preferences)
- Layer 3 Caching (user-specific, 1-hour TTL)
- AI Flow Integration (5-Layer LangGraph workflow)
"""

import logging
from datetime import datetime

import grpc

from shared.generated import strategy_pb2, strategy_pb2_grpc

from .clients.classification_client import ClassificationClient
from .clients.market_data_client import MarketDataClient
from .clients.market_regime_client import MarketRegimeClient
from .config import config
from .factor_scoring import FactorScoringEngine
from .models import RiskProfile, StockPick, UserPreferences
from .utils.cache import (
    UserCacheManager,
    build_preferences_cache_key,
    build_strategy_cache_key,
)
from .workflow.graph import create_ai_workflow

logger = logging.getLogger(__name__)


class StrategyServicer(strategy_pb2_grpc.StrategyServiceServicer):
    """gRPC servicer implementing Stock Selection Pipeline Stage 3."""

    def __init__(
        self,
        classification_client: ClassificationClient,
        market_data_client: MarketDataClient,
        regime_client: MarketRegimeClient,
        cache_manager: UserCacheManager,
    ):
        """Initialize Strategy servicer.

        Args:
            classification_client: Classification Service gRPC client
            market_data_client: Market Data Service gRPC client
            regime_client: Market Regime Service gRPC client
            cache_manager: User cache manager (Layer 3)
        """
        self.classification = classification_client
        self.market_data = market_data_client
        self.regime_client = regime_client
        self.cache = cache_manager
        self.factor_engine = FactorScoringEngine(market_data_client)

        # Initialize AI workflow
        self.ai_workflow = create_ai_workflow()

        logger.info("Strategy servicer initialized with AI workflow")

    async def get_stock_picks(
        self, user_id: str, max_picks: int = 15
    ) -> tuple[list[StockPick], str, UserPreferences]:
        """Stage 3: Factor Scoring + User Preferences.

        Args:
            user_id: User ID for preferences
            max_picks: Maximum number of picks to return

        Returns:
            Tuple of (stock_picks, regime, applied_preferences)
        """
        logger.info(f"Getting stock picks for user {user_id} (max: {max_picks})")

        # Get current regime
        regime_response = await self.regime_client.get_current_regime()
        regime = regime_response.regime

        # Get user preferences
        preferences = await self.get_preferences(user_id)

        # Get candidate symbols from Classification Service (Stage 1+2)
        candidates, _, _ = await self.classification.get_candidate_symbols(
            regime=regime, max_candidates=50
        )

        # Filter excluded sectors
        if preferences.excluded_sectors:
            candidates = [c for c in candidates if c.sector not in preferences.excluded_sectors]
            logger.info(f"Filtered candidates by excluded sectors: {len(candidates)} remaining")

        # Calculate factor scores for each candidate
        scored_picks = []
        for candidate in candidates:
            try:
                # Calculate factor scores
                factor_scores = await self.factor_engine.calculate_factor_scores(
                    candidate.symbol, regime
                )

                # Calculate final weighted score based on risk profile
                final_score = self.factor_engine.calculate_final_score(
                    factor_scores, preferences.risk_profile
                )

                # Generate rationale
                rationale = self._generate_rationale(candidate, factor_scores)

                scored_picks.append(
                    StockPick(
                        symbol=candidate.symbol,
                        sector=candidate.sector,
                        theme=candidate.theme,
                        factor_scores=factor_scores,
                        final_score=float(final_score),
                        rank=0,  # Will be set after sorting
                        rationale=rationale,
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to score {candidate.symbol}: {e}")
                continue

        # Sort by final score (descending)
        scored_picks.sort(key=lambda x: x.final_score, reverse=True)

        # Select top N picks
        top_picks = scored_picks[:max_picks]

        # Assign ranks
        for i, pick in enumerate(top_picks):
            pick.rank = i + 1

        logger.info(
            f"Stock picks completed: {len(top_picks)} picks selected "
            f"(risk profile: {preferences.risk_profile})"
        )
        return top_picks, regime, preferences

    async def get_personalized_strategy(self, user_id: str) -> tuple[dict, bool]:
        """Get complete personalized strategy (Layer 1+2+3 combined).

        Args:
            user_id: User ID

        Returns:
            Tuple of (strategy_dict, from_cache)
        """
        logger.info(f"Getting personalized strategy for user {user_id}")

        # Check Layer 3 cache (1-hour TTL)
        cache_key = build_strategy_cache_key(user_id)
        cached = await self.cache.get(cache_key)
        if cached:
            logger.info(f"Strategy cache HIT for user {user_id}")
            cached["from_cache"] = True
            return cached, True

        # Cache miss - run full pipeline
        logger.info(f"Strategy cache MISS for user {user_id}, running full pipeline")

        # Layer 1: Market Regime
        regime_response = await self.regime_client.get_current_regime()
        regime = regime_response.regime

        # Layer 2: Sectors/Themes (cached by Classification Service)
        sector_response = await self.classification.get_sector_analysis(regime)
        selected_sectors = [s.sector for s in sector_response.sectors if s.selected]

        theme_response = await self.classification.get_thematic_analysis(selected_sectors, regime)
        top_themes = [t.theme for t in theme_response.themes[:5]]

        # Layer 3: Stock Picks (user-specific)
        picks, _, preferences = await self.get_stock_picks(user_id)

        # Build response
        cached_at = datetime.utcnow().isoformat() + "Z"
        result = {
            "user_id": user_id,
            "regime": regime,
            "selected_sectors": selected_sectors,
            "top_themes": top_themes,
            "stock_picks": [
                {
                    "symbol": p.symbol,
                    "sector": p.sector,
                    "theme": p.theme,
                    "factor_scores": {
                        "momentum": p.factor_scores.momentum,
                        "value": p.factor_scores.value,
                        "quality": p.factor_scores.quality,
                        "volatility": p.factor_scores.volatility,
                        "liquidity": p.factor_scores.liquidity,
                        "sentiment": p.factor_scores.sentiment,
                    },
                    "final_score": p.final_score,
                    "rank": p.rank,
                    "rationale": p.rationale,
                }
                for p in picks
            ],
            "preferences": {
                "user_id": preferences.user_id,
                "risk_profile": preferences.risk_profile.value,
                "preferred_sectors": preferences.preferred_sectors,
                "excluded_sectors": preferences.excluded_sectors,
                "max_single_position": preferences.max_single_position,
            },
            "cached_at": cached_at,
            "from_cache": False,
        }

        # Cache result (1-hour TTL)
        await self.cache.set(cache_key, result, ttl=config.cache_ttl)

        logger.info(f"Personalized strategy generated and cached for user {user_id}")
        return result, False

    async def get_preferences(self, user_id: str) -> UserPreferences:
        """Get user preferences.

        Returns default preferences if user has not customized.

        Args:
            user_id: User ID

        Returns:
            UserPreferences
        """
        cache_key = build_preferences_cache_key(user_id)
        cached = await self.cache.get(cache_key)

        if cached:
            logger.debug(f"Preferences cache HIT for user {user_id}")
            return UserPreferences(**cached)

        # Return default preferences
        logger.debug(f"Preferences cache MISS for user {user_id}, using defaults")
        return UserPreferences(
            user_id=user_id,
            risk_profile=RiskProfile.MODERATE,
            preferred_sectors=[],
            excluded_sectors=[],
            max_single_position=0.10,  # 10%
        )

    async def update_preferences(
        self, user_id: str, preferences: UserPreferences
    ) -> UserPreferences:
        """Update user preferences.

        Args:
            user_id: User ID
            preferences: New preferences

        Returns:
            Updated preferences
        """
        logger.info(f"Updating preferences for user {user_id}")

        # Save preferences (30-day TTL)
        cache_key = build_preferences_cache_key(user_id)
        preferences_dict = {
            "user_id": preferences.user_id,
            "risk_profile": preferences.risk_profile.value,
            "preferred_sectors": preferences.preferred_sectors,
            "excluded_sectors": preferences.excluded_sectors,
            "max_single_position": preferences.max_single_position,
        }
        await self.cache.set(cache_key, preferences_dict, ttl=config.preferences_ttl)

        # Invalidate strategy cache to force refresh
        strategy_key = build_strategy_cache_key(user_id)
        await self.cache.delete(strategy_key)

        logger.info(f"Preferences updated and strategy cache invalidated for user {user_id}")
        return preferences

    async def run_ai_analysis(self, user_id: str) -> dict:
        """Run AI Flow (5-Layer LangGraph workflow).

        This executes the complete AI analysis pipeline:
        - Layer 1: Macro Analysis (FinGPT)
        - Layer 2: Technical Analysis (Claude)
        - Layer 3: Risk Assessment (Claude)
        - Layer 4: Signal Generation
        - Layer 5: Event Publishing (Redpanda)

        Args:
            user_id: User ID

        Returns:
            Final workflow state with trading signals

        Raises:
            Exception: If workflow execution fails
        """
        logger.info(f"Running AI analysis workflow for user {user_id}")

        # Get stock picks from Stage 3 (Factor Scoring)
        picks, regime, preferences = await self.get_stock_picks(user_id, max_picks=15)

        # Prepare initial state
        initial_state = {
            "user_id": user_id,
            "stock_picks": [
                {
                    "symbol": p.symbol,
                    "sector": p.sector,
                    "theme": p.theme,
                    "final_score": p.final_score,
                    "factor_scores": {
                        "momentum": p.factor_scores.momentum,
                        "value": p.factor_scores.value,
                        "quality": p.factor_scores.quality,
                        "volatility": p.factor_scores.volatility,
                        "liquidity": p.factor_scores.liquidity,
                        "sentiment": p.factor_scores.sentiment,
                    },
                }
                for p in picks
            ],
            "preferences": {
                "user_id": preferences.user_id,
                "risk_profile": preferences.risk_profile.value,
                "preferred_sectors": preferences.preferred_sectors,
                "excluded_sectors": preferences.excluded_sectors,
                "max_single_position": preferences.max_single_position,
                "regime": regime,
            },
            "technical_signals": [],
            "trading_signals": [],
        }

        # Execute workflow
        try:
            final_state = await self.ai_workflow.ainvoke(initial_state)
            logger.info(
                f"AI analysis complete for user {user_id}: "
                f"phase={final_state.get('phase')}, "
                f"signals={len(final_state.get('trading_signals', []))}"
            )
            return final_state

        except Exception as e:
            logger.error(f"AI workflow execution failed for user {user_id}: {e}", exc_info=True)
            raise

    def _generate_rationale(self, candidate, factor_scores) -> str:
        """Generate investment rationale based on factor strengths.

        Args:
            candidate: Candidate symbol
            factor_scores: Factor scores

        Returns:
            Human-readable rationale
        """
        strengths = []

        if factor_scores.momentum > 70:
            strengths.append("strong momentum")
        if factor_scores.value > 70:
            strengths.append("attractive valuation")
        if factor_scores.quality > 70:
            strengths.append("high quality")
        if factor_scores.volatility > 70:
            strengths.append("low volatility")
        if factor_scores.liquidity > 70:
            strengths.append("high liquidity")
        if factor_scores.sentiment > 70:
            strengths.append("positive sentiment")

        if strengths:
            strength_text = ", ".join(strengths)
            return f"{candidate.symbol} in {candidate.theme} theme shows {strength_text}."
        else:
            return f"{candidate.symbol} in {candidate.theme} theme shows balanced factors."

    # gRPC Handler Methods

    async def GetStockPicks(  # noqa: N802
        self,
        request: strategy_pb2.StockPicksRequest,
        context: grpc.aio.ServicerContext,
    ) -> strategy_pb2.StockPicksResponse:
        """Get stock picks with factor scoring."""
        try:
            user_id = request.user_id
            max_picks = request.max_picks or 15

            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id field is required")
                return strategy_pb2.StockPicksResponse()

            logger.info(f"GetStockPicks request: user_id={user_id}, max_picks={max_picks}")

            # Call business logic
            picks, regime, preferences = await self.get_stock_picks(user_id, max_picks)

            # Convert to proto response
            pick_protos = [
                strategy_pb2.StockPick(
                    symbol=p.symbol,
                    sector=p.sector,
                    theme=p.theme,
                    factor_scores=strategy_pb2.FactorScores(
                        momentum=p.factor_scores.momentum,
                        value=p.factor_scores.value,
                        quality=p.factor_scores.quality,
                        volatility=p.factor_scores.volatility,
                        liquidity=p.factor_scores.liquidity,
                        sentiment=p.factor_scores.sentiment,
                    ),
                    final_score=p.final_score,
                    rank=p.rank,
                    rationale=p.rationale,
                )
                for p in picks
            ]

            # Map RiskProfile to proto enum
            risk_profile_map = {
                RiskProfile.CONSERVATIVE: strategy_pb2.CONSERVATIVE,
                RiskProfile.MODERATE: strategy_pb2.MODERATE,
                RiskProfile.AGGRESSIVE: strategy_pb2.AGGRESSIVE,
            }

            preferences_proto = strategy_pb2.UserPreferences(
                user_id=preferences.user_id,
                risk_profile=risk_profile_map[preferences.risk_profile],
                preferred_sectors=preferences.preferred_sectors,
                excluded_sectors=preferences.excluded_sectors,
                max_single_position=preferences.max_single_position,
            )

            return strategy_pb2.StockPicksResponse(
                picks=pick_protos,
                regime=regime,
                applied_preferences=preferences_proto,
                generated_at=datetime.utcnow().isoformat() + "Z",
            )

        except ConnectionError as e:
            logger.error(f"Service unavailable: {e}")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Dependent service unavailable")
            return strategy_pb2.StockPicksResponse()

        except TimeoutError as e:
            logger.error(f"Service timeout: {e}")
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details("Dependent service request timed out")
            return strategy_pb2.StockPicksResponse()

        except Exception as e:
            logger.error(f"GetStockPicks error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return strategy_pb2.StockPicksResponse()

    async def GetPersonalizedStrategy(  # noqa: N802
        self,
        request: strategy_pb2.StrategyRequest,
        context: grpc.aio.ServicerContext,
    ) -> strategy_pb2.StrategyResponse:
        """Get complete personalized strategy."""
        try:
            user_id = request.user_id

            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id field is required")
                return strategy_pb2.StrategyResponse()

            logger.info(f"GetPersonalizedStrategy request: user_id={user_id}")

            # Call business logic
            result, from_cache = await self.get_personalized_strategy(user_id)

            # Convert stock picks to proto
            pick_protos = [
                strategy_pb2.StockPick(
                    symbol=p["symbol"],
                    sector=p["sector"],
                    theme=p["theme"],
                    factor_scores=strategy_pb2.FactorScores(
                        momentum=p["factor_scores"]["momentum"],
                        value=p["factor_scores"]["value"],
                        quality=p["factor_scores"]["quality"],
                        volatility=p["factor_scores"]["volatility"],
                        liquidity=p["factor_scores"]["liquidity"],
                        sentiment=p["factor_scores"]["sentiment"],
                    ),
                    final_score=p["final_score"],
                    rank=p["rank"],
                    rationale=p["rationale"],
                )
                for p in result["stock_picks"]
            ]

            # Map string risk profile to proto enum
            risk_profile_str = result["preferences"]["risk_profile"]
            risk_profile_map = {
                "CONSERVATIVE": strategy_pb2.CONSERVATIVE,
                "MODERATE": strategy_pb2.MODERATE,
                "AGGRESSIVE": strategy_pb2.AGGRESSIVE,
            }

            preferences_proto = strategy_pb2.UserPreferences(
                user_id=result["preferences"]["user_id"],
                risk_profile=risk_profile_map.get(
                    risk_profile_str, strategy_pb2.RISK_PROFILE_UNSPECIFIED
                ),
                preferred_sectors=result["preferences"]["preferred_sectors"],
                excluded_sectors=result["preferences"]["excluded_sectors"],
                max_single_position=result["preferences"]["max_single_position"],
            )

            return strategy_pb2.StrategyResponse(
                user_id=result["user_id"],
                regime=result["regime"],
                selected_sectors=result["selected_sectors"],
                top_themes=result["top_themes"],
                stock_picks=pick_protos,
                preferences=preferences_proto,
                cached_at=result["cached_at"],
                from_cache=from_cache,
            )

        except ConnectionError as e:
            logger.error(f"Service unavailable: {e}")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Dependent service unavailable")
            return strategy_pb2.StrategyResponse()

        except TimeoutError as e:
            logger.error(f"Service timeout: {e}")
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details("Dependent service request timed out")
            return strategy_pb2.StrategyResponse()

        except Exception as e:
            logger.error(f"GetPersonalizedStrategy error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return strategy_pb2.StrategyResponse()

    async def UpdatePreferences(  # noqa: N802
        self,
        request: strategy_pb2.UpdatePreferencesRequest,
        context: grpc.aio.ServicerContext,
    ) -> strategy_pb2.UpdatePreferencesResponse:
        """Update user preferences."""
        try:
            user_id = request.user_id

            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id field is required")
                return strategy_pb2.UpdatePreferencesResponse()

            logger.info(f"UpdatePreferences request: user_id={user_id}")

            # Map proto enum to internal RiskProfile
            risk_profile_map = {
                strategy_pb2.CONSERVATIVE: RiskProfile.CONSERVATIVE,
                strategy_pb2.MODERATE: RiskProfile.MODERATE,
                strategy_pb2.AGGRESSIVE: RiskProfile.AGGRESSIVE,
            }
            risk_profile = risk_profile_map.get(request.risk_profile, RiskProfile.MODERATE)

            # Create preferences object
            preferences = UserPreferences(
                user_id=user_id,
                risk_profile=risk_profile,
                preferred_sectors=list(request.preferred_sectors),
                excluded_sectors=list(request.excluded_sectors),
                max_single_position=request.max_single_position,
            )

            # Update preferences
            updated = await self.update_preferences(user_id, preferences)

            # Map back to proto enum
            reverse_map = {
                RiskProfile.CONSERVATIVE: strategy_pb2.CONSERVATIVE,
                RiskProfile.MODERATE: strategy_pb2.MODERATE,
                RiskProfile.AGGRESSIVE: strategy_pb2.AGGRESSIVE,
            }

            preferences_proto = strategy_pb2.UserPreferences(
                user_id=updated.user_id,
                risk_profile=reverse_map[updated.risk_profile],
                preferred_sectors=updated.preferred_sectors,
                excluded_sectors=updated.excluded_sectors,
                max_single_position=updated.max_single_position,
            )

            return strategy_pb2.UpdatePreferencesResponse(
                success=True,
                preferences=preferences_proto,
            )

        except Exception as e:
            logger.error(f"UpdatePreferences error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return strategy_pb2.UpdatePreferencesResponse(success=False)

    async def GetPreferences(  # noqa: N802
        self,
        request: strategy_pb2.GetPreferencesRequest,
        context: grpc.aio.ServicerContext,
    ) -> strategy_pb2.UserPreferences:
        """Get user preferences."""
        try:
            user_id = request.user_id

            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id field is required")
                return strategy_pb2.UserPreferences()

            logger.info(f"GetPreferences request: user_id={user_id}")

            # Get preferences
            preferences = await self.get_preferences(user_id)

            # Map to proto enum
            risk_profile_map = {
                RiskProfile.CONSERVATIVE: strategy_pb2.CONSERVATIVE,
                RiskProfile.MODERATE: strategy_pb2.MODERATE,
                RiskProfile.AGGRESSIVE: strategy_pb2.AGGRESSIVE,
            }

            return strategy_pb2.UserPreferences(
                user_id=preferences.user_id,
                risk_profile=risk_profile_map[preferences.risk_profile],
                preferred_sectors=preferences.preferred_sectors,
                excluded_sectors=preferences.excluded_sectors,
                max_single_position=preferences.max_single_position,
            )

        except Exception as e:
            logger.error(f"GetPreferences error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return strategy_pb2.UserPreferences()
