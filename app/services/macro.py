"""Macro Data Service — FRED API integration with 1h cache.

Provides macro economic indicators for market regime classification.
Falls back to conservative defaults when FRED API key is not configured.
"""

import asyncio
import logging

from shared.utils.redis_client import RedisClient

from ..config import settings

logger = logging.getLogger(__name__)

CACHE_KEY = "macro:indicators"

# FRED series IDs
FRED_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "unemployment_rate": "UNRATE",
    "cpi_yoy": "CPIAUCSL",
    "credit_spread": "BAMLH0A0HYM2",
}

# Conservative defaults when API unavailable
DEFAULTS: dict[str, float] = {
    "fed_funds_rate": 5.25,
    "unemployment_rate": 3.8,
    "cpi_yoy": 3.2,
    "credit_spread": 150.0,
}


class MacroService:
    """FRED API macro indicator service with Tier 1 shared caching (1h TTL)."""

    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis

    async def get_indicators(self) -> dict[str, float]:
        """Get macro economic indicators from FRED (cached 1h).

        Returns dict with fed_funds_rate, unemployment_rate, cpi_yoy, credit_spread.
        Falls back to conservative defaults when API key missing or call fails.
        """
        cached = await self.redis.get(CACHE_KEY)
        if cached and isinstance(cached, dict):
            result: dict[str, float] = cached
            return result

        indicators = await self._fetch_from_fred()

        await self.redis.setex(CACHE_KEY, settings.cache_macro_ttl, indicators)
        return indicators

    async def _fetch_from_fred(self) -> dict[str, float]:
        """Fetch indicators from FRED API. Returns defaults on failure."""
        if not settings.fred_api_key:
            logger.info("FRED API key not configured, using defaults")
            return dict(DEFAULTS)

        try:
            return await asyncio.to_thread(self._sync_fetch)
        except Exception as e:
            logger.warning("FRED API call failed, using defaults", extra={"error": str(e)})
            return dict(DEFAULTS)

    def _sync_fetch(self) -> dict[str, float]:
        """Synchronous FRED API calls (run in thread pool)."""
        from fredapi import Fred

        fred = Fred(api_key=settings.fred_api_key)
        result = dict(DEFAULTS)

        # Fed Funds Rate
        try:
            series = fred.get_series(FRED_SERIES["fed_funds_rate"])
            if not series.empty:
                result["fed_funds_rate"] = float(series.iloc[-1])
        except (ValueError, KeyError) as e:
            logger.warning("Failed to fetch fed_funds_rate", extra={"error": str(e)})

        # Unemployment Rate
        try:
            series = fred.get_series(FRED_SERIES["unemployment_rate"])
            if not series.empty:
                result["unemployment_rate"] = float(series.iloc[-1])
        except (ValueError, KeyError) as e:
            logger.warning("Failed to fetch unemployment_rate", extra={"error": str(e)})

        # CPI Year-over-Year (calculate from 12-month change)
        try:
            series = fred.get_series(FRED_SERIES["cpi_yoy"])
            if len(series) >= 13:
                current = float(series.iloc[-1])
                year_ago = float(series.iloc[-13])
                if year_ago > 0:
                    result["cpi_yoy"] = round((current - year_ago) / year_ago * 100, 1)
        except (ValueError, KeyError) as e:
            logger.warning("Failed to fetch cpi_yoy", extra={"error": str(e)})

        # Credit Spread (High Yield - Investment Grade)
        try:
            series = fred.get_series(FRED_SERIES["credit_spread"])
            if not series.empty:
                result["credit_spread"] = round(float(series.iloc[-1]) * 100, 0)
        except (ValueError, KeyError) as e:
            logger.warning("Failed to fetch credit_spread", extra={"error": str(e)})

        return result
