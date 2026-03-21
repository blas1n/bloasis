"""Strategy Service — Sequential pipeline replacing LangGraph.

Replaces: services/strategy/ (820 lines gRPC + LangGraph → ~120 lines direct)

Pipeline:
1. Market Regime (cached, Tier 1)
2. Classification / Candidates (cached, Tier 1)
3. Factor Scoring (pure computation)
4. AI Analysis — Claude 1 call (Technical + Risk merged)
5. Signal Generation (pure computation)
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from shared.ai_clients.llm_client import LLMClient
from shared.utils.redis_client import RedisClient

from ..config import settings
from ..core import factor_scoring as fs
from ..core.models import (
    AnalysisResult,
    CandidateSymbol,
    FactorScores,
    MarketRegime,
    RiskProfile,
    StockPick,
    TradingSignal,
)
from ..core.prompts.analysis import ANALYSIS_SYSTEM_PROMPT, format_analysis_prompt
from ..core.signal_generator import generate_signal
from ..core.technical_indicators import calculate_indicators, format_indicators_summary
from .classification import ClassificationService
from .market_data import MarketDataService
from .market_regime import MarketRegimeService

logger = logging.getLogger(__name__)


class StrategyService:
    """Sequential analysis pipeline replacing LangGraph 5-layer workflow."""

    def __init__(
        self,
        redis: RedisClient,
        llm: LLMClient,
        market_data: MarketDataService,
        market_regime: MarketRegimeService,
        classification: ClassificationService,
    ) -> None:
        self.redis = redis
        self.llm = llm
        self.market_data = market_data
        self.market_regime = market_regime
        self.classification = classification

    async def invalidate_user_cache(self, user_id: uuid.UUID) -> None:
        """Invalidate cached analysis for a user."""
        await self.redis.delete(f"user:{user_id}:analysis")

    async def run_analysis(
        self,
        user_id: uuid.UUID,
        risk_profile: RiskProfile = RiskProfile.MODERATE,
        preferred_sectors: list[str] | None = None,
        excluded_sectors: list[str] | None = None,
    ) -> AnalysisResult:
        """Run complete analysis pipeline.

        Args:
            user_id: User identifier.
            risk_profile: User's risk profile.
            preferred_sectors: Boost these sectors.
            excluded_sectors: Filter out these sectors.

        Returns:
            AnalysisResult with signals.
        """
        # Check user-specific cache (Tier 3, 1h)
        cache_key = f"user:{user_id}:analysis"
        cached = await self.redis.get(cache_key)
        if cached and isinstance(cached, dict):
            try:
                return AnalysisResult(**cached)
            except (ValidationError, TypeError):
                await self.redis.delete(cache_key)

        logger.info("Running analysis", extra={"user_id": user_id})

        # 1. Market regime (Tier 1 cached, 6h)
        regime = await self.market_regime.get_current()

        # 2. Candidates (Tier 1 cached, 6h)
        candidates = await self.classification.get_candidates(regime.regime)

        # Filter excluded sectors
        if excluded_sectors:
            candidates = [c for c in candidates if c.sector not in excluded_sectors]

        # 3. Factor scoring (pure computation)
        picks = await self._score_candidates(
            candidates[: settings.max_stocks_per_analysis],
            regime.regime,
            risk_profile,
        )

        # 4. AI analysis — single Claude call (Technical + Risk merged)
        ohlcv_data: dict[str, list[dict[str, Any]]] = {}
        ohlcv_summary_parts = []
        for pick in picks[:10]:
            bars = await self.market_data.get_ohlcv(pick.symbol)
            ohlcv_data[pick.symbol] = bars
            indicators = calculate_indicators(pick.symbol, bars)
            if indicators:
                ohlcv_summary_parts.append(format_indicators_summary(indicators))

        ohlcv_summary = "\n".join(ohlcv_summary_parts) or "No data available"

        stock_data = [
            {"symbol": p.symbol, "sector": p.sector, "score": p.final_score, "theme": p.theme}
            for p in picks
        ]

        analysis_result = await self._run_ai_analysis(
            stock_data,
            ohlcv_summary,
            regime,
            risk_profile,
            excluded_sectors or [],
        )

        # 5. Signal generation (pure computation)
        signals = self._generate_signals(
            analysis_result,
            ohlcv_data,
            regime.risk_level,
            risk_profile,
        )

        result = AnalysisResult(
            user_id=str(user_id),
            regime=regime,
            selected_sectors=list({c.sector for c in candidates}),
            top_themes=list({c.theme for c in candidates if c.theme})[:5],
            stock_picks=picks,
            signals=signals,
            cached_at=datetime.now(UTC).isoformat(),
        )

        # Cache user result (Tier 3, 1h)
        await self.redis.setex(cache_key, settings.cache_user_portfolio_ttl, result.model_dump())

        return result

    async def _score_candidates(
        self,
        candidates: list[CandidateSymbol],
        regime: str,
        risk_profile: RiskProfile,
    ) -> list[StockPick]:
        """Score candidates using 6-factor engine."""
        picks: list[StockPick] = []

        for candidate in candidates:
            try:
                bars = await self.market_data.get_ohlcv(candidate.symbol)
                info = await self.market_data.get_stock_info(candidate.symbol)

                scores = FactorScores(
                    momentum=fs.calculate_momentum(bars),
                    value=fs.calculate_value(
                        pe_ratio=info.get("pe_ratio"),
                        profit_margin=info.get("profit_margin"),
                        current_ratio=info.get("current_ratio"),
                    ),
                    quality=fs.calculate_quality(
                        return_on_equity=info.get("return_on_equity"),
                        debt_to_equity=info.get("debt_to_equity"),
                        profit_margin=info.get("profit_margin"),
                        current_ratio=info.get("current_ratio"),
                        market_cap=info.get("market_cap", 0),
                    ),
                    volatility=fs.calculate_volatility(bars),
                    liquidity=fs.calculate_liquidity(bars),
                    sentiment=fs.calculate_sentiment_from_momentum(fs.calculate_momentum(bars)),
                )

                final_score = fs.calculate_final_score(scores, risk_profile, regime)

                picks.append(
                    StockPick(
                        symbol=candidate.symbol,
                        sector=candidate.sector,
                        theme=candidate.theme,
                        factor_scores=scores,
                        final_score=float(final_score),
                    )
                )

            except (ValueError, RuntimeError) as e:
                logger.warning(
                    "Failed to score candidate", extra={"symbol": candidate.symbol, "error": str(e)}
                )

        # Sort by score descending, assign ranks, take top N
        picks.sort(key=lambda p: p.final_score, reverse=True)
        for i, pick in enumerate(picks):
            pick.rank = i + 1

        return picks[: settings.max_stocks_per_analysis]

    async def _run_ai_analysis(
        self,
        stock_data: list[dict[str, Any]],
        ohlcv_summary: str,
        regime: MarketRegime,
        risk_profile: RiskProfile,
        excluded_sectors: list[str],
    ) -> list[dict[str, Any]]:
        """Run unified AI analysis (Technical + Risk in one call)."""
        market_context = {
            "regime": regime.regime,
            "risk_level": regime.risk_level,
            "sector_outlook": {},
        }
        user_prefs = {
            "risk_profile": risk_profile,
            "max_single_position": settings.max_single_order,
            "excluded_sectors": excluded_sectors,
        }

        prompt = format_analysis_prompt(stock_data, ohlcv_summary, market_context, user_prefs)

        try:
            result = await self.llm.analyze(
                prompt=prompt,
                system_prompt=ANALYSIS_SYSTEM_PROMPT,
                response_format="json",
                max_tokens=8000,
            )
            if isinstance(result, list):
                return result
            result_type = type(result).__name__
            logger.warning("AI analysis returned non-list", extra={"type": result_type})
            return []
        except (RuntimeError, json.JSONDecodeError, ValueError) as e:
            logger.error("AI analysis failed", extra={"error": str(e)})
            raise RuntimeError(f"AI analysis unavailable: {e}") from e

    def _generate_signals(
        self,
        analysis_results: list[dict[str, Any]],
        ohlcv_data: dict[str, list[dict[str, Any]]],
        risk_level: str,
        risk_profile: RiskProfile,
    ) -> list[TradingSignal]:
        """Generate trading signals from AI analysis results."""
        signals = []
        for item in analysis_results:
            symbol = item.get("symbol", "")
            direction = item.get("direction", "neutral")
            strength = item.get("strength", 0.5)
            entry_price = item.get("entry_price", 0)

            if not symbol or entry_price <= 0:
                continue

            rationale = item.get("rationale", "")
            if not rationale:
                risk_note = item.get("risk_note", "")
                rationale = (
                    f"AI signal: {direction} {symbol} (strength={strength:.0%}, risk={risk_level})"
                )
                if risk_note:
                    rationale += f". {risk_note}"

            signal = generate_signal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                entry_price=Decimal(str(entry_price)),
                risk_level=risk_level,
                risk_profile=risk_profile,
                ohlcv_bars=ohlcv_data.get(symbol),
                rationale=rationale,
                sector=item.get("sector", "Unknown"),
            )
            signals.append(signal)

        return signals
