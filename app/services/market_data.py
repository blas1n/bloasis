"""Market Data Service — yfinance data with cache-aside.

Replaces: services/market-data/ (377 lines gRPC → ~120 lines direct)
"""

import asyncio
import re
from decimal import Decimal
from typing import Any

import structlog
import yfinance as yf

from shared.utils.postgres_client import PostgresClient
from shared.utils.redis_client import RedisClient

from ..config import settings
from ..shared.utils.cache import cache_aside

logger = structlog.get_logger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Z\^][A-Z0-9.\-]{0,9}$")


def _validate_symbol(symbol: str) -> None:
    """Validate ticker symbol format (1-10 chars, uppercase alphanumeric)."""
    if not _SYMBOL_RE.match(symbol):
        raise ValueError(f"Invalid symbol: {symbol}")


class MarketDataService:
    """Market data fetching with Redis cache-aside pattern."""

    def __init__(self, redis: RedisClient, postgres: PostgresClient) -> None:
        self.redis = redis
        self.postgres = postgres

    @cache_aside(
        key_fn=lambda self, symbol, period="3mo", interval="1d": (
            f"ohlcv:{symbol}:{period}:{interval}"
        ),
        ttl=settings.cache_ohlcv_ttl,
    )
    async def get_ohlcv(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> list[dict[str, Any]]:
        """Get OHLCV data for a symbol."""
        _validate_symbol(symbol)
        return await asyncio.to_thread(self._sync_get_ohlcv, symbol, period, interval)

    def _sync_get_ohlcv(self, symbol: str, period: str, interval: str) -> list[dict[str, Any]]:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            return []

        bars = []
        for ts, row in df.iterrows():
            bars.append(
                {
                    "timestamp": ts.isoformat(),
                    "open": Decimal(str(row["Open"])),
                    "high": Decimal(str(row["High"])),
                    "low": Decimal(str(row["Low"])),
                    "close": Decimal(str(row["Close"])),
                    "volume": int(row["Volume"]),
                }
            )
        return bars

    @cache_aside(
        key_fn=lambda self, symbol: f"stockinfo:{symbol}", ttl=settings.cache_stock_info_ttl
    )
    async def get_stock_info(self, symbol: str) -> dict[str, Any]:
        """Get stock metadata (sector, PE, market cap, etc.)."""
        _validate_symbol(symbol)
        return await asyncio.to_thread(self._sync_get_stock_info, symbol)

    def _sync_get_stock_info(self, symbol: str) -> dict[str, Any]:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        return {
            "symbol": symbol,
            "name": info.get("shortName", ""),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE"),
            "profit_margin": info.get("profitMargins"),
            "current_ratio": info.get("currentRatio"),
            "return_on_equity": info.get("returnOnEquity"),
            "debt_to_equity": info.get("debtToEquity"),
            "dividend_yield": info.get("dividendYield"),
        }

    async def get_vix(self) -> float:
        """Get current VIX value."""
        try:
            cached = await self.redis.get("market:vix")
            if cached is not None:
                return float(cached)

            vix = await asyncio.to_thread(self._sync_get_vix)
            await self.redis.setex("market:vix", 300, str(vix))
            return vix
        except (TimeoutError, ValueError) as e:
            logger.warning("vix_fetch_failed", error=str(e))

        return 20.0  # Default

    def _sync_get_vix(self) -> float:
        ticker = yf.Ticker("^VIX")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return 20.0

    async def get_previous_close(self, symbol: str) -> Decimal:
        """Get previous day's closing price for a symbol."""
        cache_key = f"prevclose:{symbol}"
        cached = await self.redis.get(cache_key)
        if cached is not None:
            return Decimal(str(cached))

        try:
            prev_close = await asyncio.to_thread(self._sync_get_previous_close, symbol)
            if prev_close is not None:
                result = Decimal(str(prev_close))
                await self.redis.setex(cache_key, settings.cache_ohlcv_ttl, str(result))
                return result
        except (TimeoutError, ValueError, KeyError) as e:
            logger.warning("previous_close_fetch_failed", symbol=symbol, error=str(e))

        return Decimal("0")

    def _sync_get_previous_close(self, symbol: str) -> float | None:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        value = info.get("previousClose")
        return float(value) if value is not None else None

    async def get_average_volume(self, symbol: str, days: int = 20) -> float:
        """Get average daily volume for a symbol."""
        bars = await self.get_ohlcv(symbol, period="1mo", interval="1d")
        if not bars:
            return 0.0
        recent = bars[-days:]
        return sum(b["volume"] for b in recent) / len(recent) if recent else 0.0
