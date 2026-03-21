"""Market Regime Service — Claude classification with 6h cache.

Replaces: services/market-regime/ (515 lines gRPC → ~90 lines direct)
Uses core/regime_classifier.py for pure parsing logic.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from shared.ai_clients.llm_client import LLMClient
from shared.utils.postgres_client import PostgresClient
from shared.utils.redis_client import RedisClient

from ..config import settings
from ..core.models import MarketRegime, MarketRegimeIndicators, RegimeType, RiskLevel
from ..core.prompts.regime import REGIME_SYSTEM_PROMPT, format_regime_prompt
from ..core.regime_classifier import calculate_risk_level, parse_regime_response
from .macro import MacroService

logger = logging.getLogger(__name__)

CACHE_KEY = "market:regime:current"


class MarketRegimeService:
    """Market regime classification with Tier 1 shared caching (6h TTL)."""

    def __init__(
        self,
        redis: RedisClient,
        postgres: PostgresClient,
        llm: LLMClient,
        macro_svc: MacroService | None = None,
    ) -> None:
        self.redis = redis
        self.postgres = postgres
        self.llm = llm
        self.macro_svc = macro_svc

    async def get_current(self, trigger: str = "baseline") -> MarketRegime:
        """Get current market regime (from cache or fresh classification).

        Args:
            trigger: What caused this classification.

        Returns:
            MarketRegime with classification results.
        """
        # Check cache
        cached = await self.redis.get(CACHE_KEY)
        if cached and isinstance(cached, dict):
            try:
                return MarketRegime(**cached)
            except (ValidationError, TypeError):
                await self.redis.delete(CACHE_KEY)

        # Classify
        regime = await self._classify(trigger)

        # Cache (Tier 1 shared): successful regime → 6h, fallback → 5min (retry soon)
        ttl = settings.cache_regime_ttl if regime.trigger != "fallback" else 300
        try:
            await self.redis.setex(CACHE_KEY, ttl, regime.model_dump())
        except Exception:
            logger.warning("Failed to cache regime result", exc_info=True)

        return regime

    async def _classify(self, trigger: str) -> MarketRegime:
        """Run Claude classification."""
        try:
            market_data = await self._fetch_market_data()
            macro = await self._fetch_macro_indicators()

            prompt = format_regime_prompt(market_data, macro)

            raw = await self.llm.analyze(
                prompt=prompt,
                system_prompt=REGIME_SYSTEM_PROMPT,
                response_format="json",
                max_tokens=1024,
            )

            result = parse_regime_response(raw)
            vix = market_data.get("vix", 20.0)
            risk_level = calculate_risk_level(result["regime"], vix)

            return MarketRegime(
                regime=RegimeType(result["regime"]),
                confidence=result["confidence"],
                timestamp=datetime.now(UTC).isoformat(),
                trigger=trigger,
                reasoning=result["reasoning"],
                risk_level=risk_level,
                indicators=MarketRegimeIndicators(
                    vix=vix,
                    sp500_trend=market_data.get("sp500_trend", "neutral"),
                    yield_curve=str(macro.get("yield_curve_10y_2y", 0.0)),
                    credit_spreads=market_data.get("credit_spreads", "normal"),
                ),
            )

        except (RuntimeError, ValueError, ValidationError, KeyError, ConnectionError, OSError) as e:
            logger.error(
                "Regime classification failed (expected)",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return self._fallback_regime()
        except Exception as e:
            logger.error(
                "Regime classification failed (unexpected: %s)",
                type(e).__name__,
                exc_info=True,
            )
            return self._fallback_regime()

    async def _fetch_market_data(self) -> dict[str, Any]:
        """Fetch VIX and S&P 500 data via yfinance (run in thread to avoid blocking)."""
        return await asyncio.to_thread(self._sync_fetch_market_data)

    def _sync_fetch_market_data(self) -> dict[str, Any]:
        """Synchronous yfinance calls for VIX and S&P 500."""
        import yfinance as yf

        data: dict[str, Any] = {"vix": 20.0, "sp500_1m_change": 0.0, "sp500_trend": "neutral"}

        try:
            vix_ticker = yf.Ticker("^VIX")
            vix_hist = vix_ticker.history(period="1d")
            if not vix_hist.empty:
                data["vix"] = float(vix_hist["Close"].iloc[-1])

            sp_ticker = yf.Ticker("^GSPC")
            sp_hist = sp_ticker.history(period="1mo")
            if len(sp_hist) >= 2:
                change = (
                    (sp_hist["Close"].iloc[-1] - sp_hist["Close"].iloc[0])
                    / sp_hist["Close"].iloc[0]
                    * 100
                )
                data["sp500_1m_change"] = round(float(change), 2)
                data["sp500_trend"] = "up" if change > 0 else "down"
        except Exception as e:
            logger.warning("Market data fetch failed", extra={"error": str(e)})

        return data

    async def _fetch_macro_indicators(self) -> dict[str, Any]:
        """Fetch macro economic indicators from FRED + yfinance treasury yields."""
        # Get FRED indicators via MacroService
        if self.macro_svc:
            indicators = await self.macro_svc.get_indicators()
        else:
            indicators = {
                "fed_funds_rate": 5.25,
                "unemployment_rate": 3.8,
                "cpi_yoy": 3.2,
                "credit_spread": 150.0,
            }

        # Treasury yield spread from yfinance (real-time, not available via FRED)
        indicators["yield_curve_10y_2y"] = await self._fetch_yield_spread()

        return indicators

    async def _fetch_yield_spread(self) -> float:
        """Fetch 10Y-2Y treasury yield spread from yfinance (run in thread)."""
        return await asyncio.to_thread(self._sync_fetch_yield_spread)

    def _sync_fetch_yield_spread(self) -> float:
        """Synchronous yfinance calls for treasury yield spread."""
        import yfinance as yf

        try:
            tnx = yf.Ticker("^TNX")
            tnx_hist = tnx.history(period="1d")
            if not tnx_hist.empty:
                yield_10y = float(tnx_hist["Close"].iloc[-1])

                irx = yf.Ticker("^IRX")
                irx_hist = irx.history(period="1d")
                if not irx_hist.empty:
                    yield_2y_proxy = float(irx_hist["Close"].iloc[-1])
                    return round(yield_10y - yield_2y_proxy, 2)
        except Exception as e:
            logger.warning("Yield spread fetch failed", extra={"error": str(e)})

        return 0.5

    def _fallback_regime(self) -> MarketRegime:
        """Return conservative default when classification fails."""
        return MarketRegime(
            regime=RegimeType("sideways"),
            confidence=0.5,
            timestamp=datetime.now(UTC).isoformat(),
            trigger="fallback",
            reasoning="Classification unavailable — using conservative default",
            risk_level=RiskLevel.MEDIUM,
        )
