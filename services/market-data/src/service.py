"""Market Data gRPC service implementation."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Optional

import grpc
import pandas as pd
from shared.generated import market_data_pb2, market_data_pb2_grpc

from .data_fetcher import MarketDataFetcher

if TYPE_CHECKING:
    from shared.utils import RedisClient

    from .repository import MarketDataRepository

logger = logging.getLogger(__name__)


class MarketDataServicer(market_data_pb2_grpc.MarketDataServiceServicer):
    """gRPC servicer for Market Data Service."""

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        data_fetcher: Optional[MarketDataFetcher] = None,
        repository: Optional[MarketDataRepository] = None,
        cache_ttl: int = 300,
    ) -> None:
        """Initialize the servicer.

        Args:
            redis_client: Redis client for caching (optional)
            data_fetcher: MarketDataFetcher instance
            repository: MarketDataRepository for database access (optional)
            cache_ttl: Cache TTL in seconds (default 5 minutes)
        """
        self.redis = redis_client
        self.fetcher = data_fetcher or MarketDataFetcher()
        self.repository = repository
        self.cache_ttl = cache_ttl

    def _get_cache_key(self, prefix: str, *args: str) -> str:
        """Generate cache key."""
        return f"market-data:{prefix}:{':'.join(args)}"

    async def _get_cached(self, key: str) -> Optional[str]:
        """Get value from cache."""
        if self.redis:
            try:
                return await self.redis.get(key)
            except Exception as e:
                logger.warning(f"Cache get failed: {e}")
        return None

    async def _set_cached(self, key: str, value: str) -> None:
        """Set value in cache."""
        if self.redis:
            try:
                await self.redis.setex(key, self.cache_ttl, value)
            except Exception as e:
                logger.warning(f"Cache set failed: {e}")

    def _df_to_bars(self, df: pd.DataFrame) -> list[market_data_pb2.OHLCVBar]:
        """Convert DataFrame to list of OHLCVBar proto messages."""
        bars = []
        for _, row in df.iterrows():
            bar = market_data_pb2.OHLCVBar(
                timestamp=str(row.get("timestamp", "")),
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=int(row.get("volume", 0)),
            )
            # Set adj_close if available
            if "adj_close" in row and pd.notna(row["adj_close"]):
                bar.adj_close = float(row["adj_close"])
            bars.append(bar)
        return bars

    async def GetOHLCV(
        self,
        request: market_data_pb2.GetOHLCVRequest,
        context: grpc.aio.ServicerContext,
    ) -> market_data_pb2.GetOHLCVResponse:
        """Get OHLCV data for a symbol."""
        symbol = request.symbol.upper()
        interval = request.interval or "1d"
        period = request.period or "1mo"
        start_date = request.start_date if request.HasField("start_date") else None
        end_date = request.end_date if request.HasField("end_date") else None

        # Generate cache key
        cache_key = self._get_cache_key(
            "ohlcv",
            symbol,
            interval,
            period or "",
            start_date or "",
            end_date or "",
        )

        # Check cache
        cached = await self._get_cached(cache_key)
        if cached:
            logger.debug(f"Cache hit for {symbol} OHLCV")
            data = json.loads(cached)
            return market_data_pb2.GetOHLCVResponse(
                symbol=symbol,
                interval=interval,
                bars=[market_data_pb2.OHLCVBar(**bar) for bar in data["bars"]],
                total_bars=data["total_bars"],
            )

        try:
            # Fetch data
            df = self.fetcher.get_ohlcv(
                symbol=symbol,
                interval=interval,
                period=period,
                start_date=start_date,
                end_date=end_date,
            )

            # Convert to proto
            bars = self._df_to_bars(df)
            response = market_data_pb2.GetOHLCVResponse(
                symbol=symbol,
                interval=interval,
                bars=bars,
                total_bars=len(bars),
            )

            # Cache result
            cache_data = {
                "bars": [
                    {
                        "timestamp": bar.timestamp,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ],
                "total_bars": len(bars),
            }
            await self._set_cached(cache_key, json.dumps(cache_data))

            return response

        except ValueError as e:
            logger.error(f"GetOHLCV error: {e}")
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        except Exception as e:
            logger.error(f"GetOHLCV unexpected error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetStockInfo(
        self,
        request: market_data_pb2.GetStockInfoRequest,
        context: grpc.aio.ServicerContext,
    ) -> market_data_pb2.GetStockInfoResponse:
        """Get stock info/metadata."""
        symbol = request.symbol.upper()

        # Generate cache key
        cache_key = self._get_cache_key("info", symbol)

        # Check cache
        cached = await self._get_cached(cache_key)
        if cached:
            logger.debug(f"Cache hit for {symbol} info")
            data = json.loads(cached)
            response = market_data_pb2.GetStockInfoResponse(
                symbol=data["symbol"],
                name=data["name"],
                sector=data["sector"],
                industry=data["industry"],
                exchange=data["exchange"],
                currency=data["currency"],
                market_cap=data["market_cap"],
            )
            if data.get("pe_ratio") is not None:
                response.pe_ratio = data["pe_ratio"]
            if data.get("dividend_yield") is not None:
                response.dividend_yield = data["dividend_yield"]
            if data.get("fifty_two_week_high") is not None:
                response.fifty_two_week_high = data["fifty_two_week_high"]
            if data.get("fifty_two_week_low") is not None:
                response.fifty_two_week_low = data["fifty_two_week_low"]
            if data.get("return_on_equity") is not None:
                response.return_on_equity = data["return_on_equity"]
            if data.get("debt_to_equity") is not None:
                response.debt_to_equity = data["debt_to_equity"]
            if data.get("current_ratio") is not None:
                response.current_ratio = data["current_ratio"]
            if data.get("profit_margin") is not None:
                response.profit_margin = data["profit_margin"]
            return response

        try:
            # Fetch data
            info = self.fetcher.get_stock_info(symbol)

            # Build response
            response = market_data_pb2.GetStockInfoResponse(
                symbol=info["symbol"],
                name=info["name"],
                sector=info["sector"],
                industry=info["industry"],
                exchange=info["exchange"],
                currency=info["currency"],
                market_cap=info["market_cap"],
            )
            if info.get("pe_ratio") is not None:
                response.pe_ratio = info["pe_ratio"]
            if info.get("dividend_yield") is not None:
                response.dividend_yield = info["dividend_yield"]
            if info.get("fifty_two_week_high") is not None:
                response.fifty_two_week_high = info["fifty_two_week_high"]
            if info.get("fifty_two_week_low") is not None:
                response.fifty_two_week_low = info["fifty_two_week_low"]
            if info.get("return_on_equity") is not None:
                response.return_on_equity = info["return_on_equity"]
            if info.get("debt_to_equity") is not None:
                response.debt_to_equity = info["debt_to_equity"]
            if info.get("current_ratio") is not None:
                response.current_ratio = info["current_ratio"]
            if info.get("profit_margin") is not None:
                response.profit_margin = info["profit_margin"]

            # Cache result
            await self._set_cached(cache_key, json.dumps(info))

            return response

        except ValueError as e:
            logger.error(f"GetStockInfo error: {e}")
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        except Exception as e:
            logger.error(f"GetStockInfo unexpected error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetBatchOHLCV(
        self,
        request: market_data_pb2.GetBatchOHLCVRequest,
        context: grpc.aio.ServicerContext,
    ) -> market_data_pb2.GetBatchOHLCVResponse:
        """Get OHLCV data for multiple symbols."""
        symbols = [s.upper() for s in request.symbols]
        interval = request.interval or "1d"
        period = request.period or "1mo"

        try:
            # Fetch data
            results, failed = self.fetcher.get_batch_ohlcv(
                symbols=symbols,
                interval=interval,
                period=period,
            )

            # Build response
            response = market_data_pb2.GetBatchOHLCVResponse(
                failed_symbols=failed,
            )

            for symbol, df in results.items():
                bars = self._df_to_bars(df)
                response.data[symbol].CopyFrom(
                    market_data_pb2.GetOHLCVResponse(
                        symbol=symbol,
                        interval=interval,
                        bars=bars,
                        total_bars=len(bars),
                    )
                )

            return response

        except Exception as e:
            logger.error(f"GetBatchOHLCV error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def SyncSymbol(
        self,
        request: market_data_pb2.SyncSymbolRequest,
        context: grpc.aio.ServicerContext,
    ) -> market_data_pb2.SyncSymbolResponse:
        """Sync symbol data from yfinance to TimescaleDB."""
        symbol = request.symbol.upper()
        interval = request.interval or "1d"
        full_refresh = request.full_refresh

        if not self.repository:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "Database repository not configured",
            )
            return market_data_pb2.SyncSymbolResponse()

        try:
            # Sync OHLCV data
            bars_synced = await self.fetcher.fetch_and_store_ohlcv(
                symbol=symbol,
                interval=interval,
                repository=self.repository,
                full_refresh=full_refresh,
            )

            # Sync stock info
            stock_info_updated = await self.fetcher.sync_stock_info(
                symbol=symbol,
                repository=self.repository,
            )

            logger.info(
                f"Synced {symbol}: {bars_synced} bars, stock_info={stock_info_updated}"
            )

            return market_data_pb2.SyncSymbolResponse(
                symbol=symbol,
                bars_synced=bars_synced,
                stock_info_updated=stock_info_updated,
            )

        except ValueError as e:
            logger.error(f"SyncSymbol error: {e}")
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
            return market_data_pb2.SyncSymbolResponse()

        except Exception as e:
            logger.error(f"SyncSymbol unexpected error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")
            return market_data_pb2.SyncSymbolResponse()

    async def ListSymbols(
        self,
        request: market_data_pb2.ListSymbolsRequest,
        context: grpc.aio.ServicerContext,
    ) -> market_data_pb2.ListSymbolsResponse:
        """List stored symbols with optional sector filter."""
        if not self.repository:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "Database repository not configured",
            )
            return market_data_pb2.ListSymbolsResponse()

        try:
            sector = request.sector if request.HasField("sector") else None
            limit = request.limit if request.HasField("limit") else 100

            symbols, total = await self.repository.list_symbols(
                sector=sector,
                limit=limit,
            )

            return market_data_pb2.ListSymbolsResponse(
                symbols=symbols,
                total=total,
            )

        except Exception as e:
            logger.error(f"ListSymbols error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")
            return market_data_pb2.ListSymbolsResponse()
