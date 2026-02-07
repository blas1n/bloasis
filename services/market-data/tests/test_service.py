"""
Unit tests for MarketDataServicer gRPC implementation.

All external dependencies (Redis, yfinance, PostgreSQL) are mocked.
Target: 80%+ code coverage for service.py.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import grpc
import pandas as pd
import pytest

from src.data_fetcher import MarketDataFetcher
from src.service import MarketDataServicer


class TestMarketDataServicer:
    """Tests for MarketDataServicer gRPC service."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        return mock

    @pytest.fixture
    def mock_fetcher(self) -> MagicMock:
        """Create mock MarketDataFetcher."""
        mock = MagicMock(spec=MarketDataFetcher)
        return mock

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock MarketDataRepository."""
        mock = AsyncMock()
        mock.get_latest_ohlcv_time = AsyncMock(return_value=None)
        mock.save_ohlcv = AsyncMock(return_value=5)
        mock.save_stock_info = AsyncMock(return_value=True)
        mock.list_symbols = AsyncMock(return_value=(["AAPL", "MSFT"], 2))
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock(spec=grpc.aio.ServicerContext)
        context.abort = AsyncMock(side_effect=grpc.RpcError())
        return context

    @pytest.fixture
    def servicer(
        self, mock_redis: AsyncMock, mock_fetcher: MagicMock
    ) -> MarketDataServicer:
        """Create a MarketDataServicer with mocked dependencies."""
        return MarketDataServicer(
            redis_client=mock_redis,
            data_fetcher=mock_fetcher,
            repository=None,
            cache_ttl=300,
        )

    @pytest.fixture
    def servicer_with_repo(
        self,
        mock_redis: AsyncMock,
        mock_fetcher: MagicMock,
        mock_repository: AsyncMock,
    ) -> MarketDataServicer:
        """Create a MarketDataServicer with repository."""
        return MarketDataServicer(
            redis_client=mock_redis,
            data_fetcher=mock_fetcher,
            repository=mock_repository,
            cache_ttl=300,
        )

    @pytest.fixture
    def sample_ohlcv_df(self) -> pd.DataFrame:
        """Create sample OHLCV DataFrame."""
        return pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="D"),
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [104.0, 105.0, 106.0],
            "volume": [1000000, 1100000, 1200000],
            "adj_close": [104.0, 105.0, 106.0],
        })


class TestCacheKeyGeneration(TestMarketDataServicer):
    """Tests for cache key generation."""

    def test_get_cache_key(self, servicer: MarketDataServicer) -> None:
        """Should generate correct cache key."""
        key = servicer._get_cache_key("ohlcv", "AAPL", "1d", "1mo")
        assert key == "market-data:ohlcv:AAPL:1d:1mo"

    def test_get_cache_key_empty_args(self, servicer: MarketDataServicer) -> None:
        """Should handle empty args."""
        key = servicer._get_cache_key("info", "AAPL")
        assert key == "market-data:info:AAPL"


class TestCacheOperations(TestMarketDataServicer):
    """Tests for cache get/set operations."""

    @pytest.mark.asyncio
    async def test_get_cached_hit(
        self, servicer: MarketDataServicer, mock_redis: AsyncMock
    ) -> None:
        """Should return cached value on hit."""
        mock_redis.get.return_value = '{"data": "test"}'
        result = await servicer._get_cached("test:key")
        assert result == '{"data": "test"}'
        mock_redis.get.assert_called_once_with("test:key")

    @pytest.mark.asyncio
    async def test_get_cached_miss(
        self, servicer: MarketDataServicer, mock_redis: AsyncMock
    ) -> None:
        """Should return None on cache miss."""
        mock_redis.get.return_value = None
        result = await servicer._get_cached("test:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_no_redis(self, mock_fetcher: MagicMock) -> None:
        """Should return None when Redis not configured."""
        servicer = MarketDataServicer(
            redis_client=None,
            data_fetcher=mock_fetcher,
        )
        result = await servicer._get_cached("test:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_error(
        self, servicer: MarketDataServicer, mock_redis: AsyncMock
    ) -> None:
        """Should return None and log warning on Redis error."""
        mock_redis.get.side_effect = Exception("Redis connection failed")
        result = await servicer._get_cached("test:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_cached_success(
        self, servicer: MarketDataServicer, mock_redis: AsyncMock
    ) -> None:
        """Should set value in cache."""
        await servicer._set_cached("test:key", '{"data": "test"}')
        mock_redis.setex.assert_called_once_with("test:key", 300, '{"data": "test"}')

    @pytest.mark.asyncio
    async def test_set_cached_no_redis(self, mock_fetcher: MagicMock) -> None:
        """Should silently skip when Redis not configured."""
        servicer = MarketDataServicer(
            redis_client=None,
            data_fetcher=mock_fetcher,
        )
        # Should not raise
        await servicer._set_cached("test:key", '{"data": "test"}')

    @pytest.mark.asyncio
    async def test_set_cached_error(
        self, servicer: MarketDataServicer, mock_redis: AsyncMock
    ) -> None:
        """Should log warning on Redis error."""
        mock_redis.setex.side_effect = Exception("Redis connection failed")
        # Should not raise
        await servicer._set_cached("test:key", '{"data": "test"}')


class TestDfToBars(TestMarketDataServicer):
    """Tests for DataFrame to protobuf conversion."""

    def test_df_to_bars_success(
        self, servicer: MarketDataServicer, sample_ohlcv_df: pd.DataFrame
    ) -> None:
        """Should convert DataFrame to list of OHLCVBar."""
        bars = servicer._df_to_bars(sample_ohlcv_df)
        assert len(bars) == 3
        assert bars[0].open == 100.0
        assert bars[0].close == 104.0
        assert bars[0].volume == 1000000
        assert bars[0].adj_close == 104.0

    def test_df_to_bars_empty(self, servicer: MarketDataServicer) -> None:
        """Should return empty list for empty DataFrame."""
        df = pd.DataFrame()
        bars = servicer._df_to_bars(df)
        assert bars == []

    def test_df_to_bars_missing_adj_close(
        self, servicer: MarketDataServicer
    ) -> None:
        """Should handle missing adj_close column."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-01"],
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [104.0],
            "volume": [1000000],
        })
        bars = servicer._df_to_bars(df)
        assert len(bars) == 1
        # adj_close should not be set when column is missing


class TestGetOHLCV(TestMarketDataServicer):
    """Tests for GetOHLCV RPC."""

    @pytest.mark.asyncio
    async def test_get_ohlcv_cache_hit(
        self,
        servicer: MarketDataServicer,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return cached data on cache hit."""
        from shared.generated import market_data_pb2

        cached_data = {
            "bars": [
                {
                    "timestamp": "2024-01-01",
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 104.0,
                    "volume": 1000000,
                }
            ],
            "total_bars": 1,
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        request = market_data_pb2.GetOHLCVRequest(
            symbol="AAPL",
            interval="1d",
            period="1mo",
        )
        response = await servicer.GetOHLCV(request, mock_context)

        assert response.symbol == "AAPL"
        assert response.interval == "1d"
        assert response.total_bars == 1
        assert len(response.bars) == 1
        assert response.bars[0].open == 100.0

    @pytest.mark.asyncio
    async def test_get_ohlcv_cache_miss(
        self,
        servicer: MarketDataServicer,
        mock_redis: AsyncMock,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
        sample_ohlcv_df: pd.DataFrame,
    ) -> None:
        """Should fetch and cache data on cache miss."""
        from shared.generated import market_data_pb2

        mock_redis.get.return_value = None
        mock_fetcher.get_ohlcv.return_value = sample_ohlcv_df

        request = market_data_pb2.GetOHLCVRequest(
            symbol="aapl",  # Test lowercase conversion
            interval="1d",
            period="1mo",
        )
        response = await servicer.GetOHLCV(request, mock_context)

        assert response.symbol == "AAPL"
        assert response.total_bars == 3
        mock_fetcher.get_ohlcv.assert_called_once_with(
            symbol="AAPL",
            interval="1d",
            period="1mo",
            start_date=None,
            end_date=None,
        )
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_ohlcv_with_dates(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
        sample_ohlcv_df: pd.DataFrame,
    ) -> None:
        """Should pass start/end dates to fetcher."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_ohlcv.return_value = sample_ohlcv_df

        request = market_data_pb2.GetOHLCVRequest(
            symbol="AAPL",
            interval="1d",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        response = await servicer.GetOHLCV(request, mock_context)

        assert response.symbol == "AAPL"
        mock_fetcher.get_ohlcv.assert_called_once_with(
            symbol="AAPL",
            interval="1d",
            period="1mo",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

    @pytest.mark.asyncio
    async def test_get_ohlcv_value_error(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with INVALID_ARGUMENT on ValueError."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_ohlcv.side_effect = ValueError("Invalid symbol")

        request = market_data_pb2.GetOHLCVRequest(
            symbol="INVALID",
            interval="1d",
            period="1mo",
        )

        with pytest.raises(grpc.RpcError):
            await servicer.GetOHLCV(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INVALID_ARGUMENT

    @pytest.mark.asyncio
    async def test_get_ohlcv_internal_error(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with INTERNAL on unexpected error."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_ohlcv.side_effect = Exception("Network error")

        request = market_data_pb2.GetOHLCVRequest(
            symbol="AAPL",
            interval="1d",
            period="1mo",
        )

        with pytest.raises(grpc.RpcError):
            await servicer.GetOHLCV(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INTERNAL

    @pytest.mark.asyncio
    async def test_get_ohlcv_default_values(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
        sample_ohlcv_df: pd.DataFrame,
    ) -> None:
        """Should use default interval and period when not provided."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_ohlcv.return_value = sample_ohlcv_df

        request = market_data_pb2.GetOHLCVRequest(symbol="AAPL")
        await servicer.GetOHLCV(request, mock_context)

        mock_fetcher.get_ohlcv.assert_called_once_with(
            symbol="AAPL",
            interval="1d",
            period="1mo",
            start_date=None,
            end_date=None,
        )


class TestGetStockInfo(TestMarketDataServicer):
    """Tests for GetStockInfo RPC."""

    @pytest.fixture
    def sample_stock_info(self) -> dict:
        """Create sample stock info."""
        return {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NASDAQ",
            "currency": "USD",
            "market_cap": 2800000000000,
            "pe_ratio": 28.5,
            "dividend_yield": 0.005,
            "fifty_two_week_high": 200.0,
            "fifty_two_week_low": 150.0,
            "return_on_equity": 0.18,
            "debt_to_equity": 1.5,
            "current_ratio": 1.5,
            "profit_margin": 0.25,
        }

    @pytest.mark.asyncio
    async def test_get_stock_info_cache_hit(
        self,
        servicer: MarketDataServicer,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
        sample_stock_info: dict,
    ) -> None:
        """Should return cached stock info on cache hit."""
        from shared.generated import market_data_pb2

        mock_redis.get.return_value = json.dumps(sample_stock_info)

        request = market_data_pb2.GetStockInfoRequest(symbol="AAPL")
        response = await servicer.GetStockInfo(request, mock_context)

        assert response.symbol == "AAPL"
        assert response.name == "Apple Inc."
        assert response.sector == "Technology"
        assert response.market_cap == 2800000000000
        assert response.pe_ratio == 28.5
        assert response.return_on_equity == 0.18

    @pytest.mark.asyncio
    async def test_get_stock_info_cache_hit_partial_data(
        self,
        servicer: MarketDataServicer,
        mock_redis: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should handle cached data with missing optional fields."""
        from shared.generated import market_data_pb2

        cached_data = {
            "symbol": "TEST",
            "name": "Test Inc.",
            "sector": "Technology",
            "industry": "Software",
            "exchange": "NASDAQ",
            "currency": "USD",
            "market_cap": 1000000000,
            # Missing optional fields
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        request = market_data_pb2.GetStockInfoRequest(symbol="TEST")
        response = await servicer.GetStockInfo(request, mock_context)

        assert response.symbol == "TEST"
        assert response.name == "Test Inc."
        # Optional fields should not be set

    @pytest.mark.asyncio
    async def test_get_stock_info_cache_miss(
        self,
        servicer: MarketDataServicer,
        mock_redis: AsyncMock,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
        sample_stock_info: dict,
    ) -> None:
        """Should fetch and cache stock info on cache miss."""
        from shared.generated import market_data_pb2

        mock_redis.get.return_value = None
        mock_fetcher.get_stock_info.return_value = sample_stock_info

        request = market_data_pb2.GetStockInfoRequest(symbol="aapl")
        response = await servicer.GetStockInfo(request, mock_context)

        assert response.symbol == "AAPL"
        assert response.name == "Apple Inc."
        mock_fetcher.get_stock_info.assert_called_once_with("AAPL")
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stock_info_value_error(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with INVALID_ARGUMENT on ValueError."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_stock_info.side_effect = ValueError("Symbol not found")

        request = market_data_pb2.GetStockInfoRequest(symbol="INVALID")

        with pytest.raises(grpc.RpcError):
            await servicer.GetStockInfo(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INVALID_ARGUMENT

    @pytest.mark.asyncio
    async def test_get_stock_info_internal_error(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with INTERNAL on unexpected error."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_stock_info.side_effect = Exception("Network error")

        request = market_data_pb2.GetStockInfoRequest(symbol="AAPL")

        with pytest.raises(grpc.RpcError):
            await servicer.GetStockInfo(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INTERNAL


class TestGetBatchOHLCV(TestMarketDataServicer):
    """Tests for GetBatchOHLCV RPC."""

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_success(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
        sample_ohlcv_df: pd.DataFrame,
    ) -> None:
        """Should return data for multiple symbols."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_batch_ohlcv.return_value = (
            {"AAPL": sample_ohlcv_df, "MSFT": sample_ohlcv_df},
            [],
        )

        request = market_data_pb2.GetBatchOHLCVRequest(
            symbols=["AAPL", "MSFT"],
            interval="1d",
            period="1mo",
        )
        response = await servicer.GetBatchOHLCV(request, mock_context)

        assert "AAPL" in response.data
        assert "MSFT" in response.data
        assert len(response.failed_symbols) == 0
        assert response.data["AAPL"].total_bars == 3

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_partial_failure(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
        sample_ohlcv_df: pd.DataFrame,
    ) -> None:
        """Should handle partial failures."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_batch_ohlcv.return_value = (
            {"AAPL": sample_ohlcv_df},
            ["INVALID"],
        )

        request = market_data_pb2.GetBatchOHLCVRequest(
            symbols=["AAPL", "INVALID"],
            interval="1d",
            period="1mo",
        )
        response = await servicer.GetBatchOHLCV(request, mock_context)

        assert "AAPL" in response.data
        assert "INVALID" in response.failed_symbols

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_lowercase_symbols(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
        sample_ohlcv_df: pd.DataFrame,
    ) -> None:
        """Should convert symbols to uppercase."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_batch_ohlcv.return_value = (
            {"AAPL": sample_ohlcv_df},
            [],
        )

        request = market_data_pb2.GetBatchOHLCVRequest(
            symbols=["aapl"],
            interval="1d",
            period="1mo",
        )
        await servicer.GetBatchOHLCV(request, mock_context)

        mock_fetcher.get_batch_ohlcv.assert_called_once_with(
            symbols=["AAPL"],
            interval="1d",
            period="1mo",
        )

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_internal_error(
        self,
        servicer: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with INTERNAL on error."""
        from shared.generated import market_data_pb2

        mock_fetcher.get_batch_ohlcv.side_effect = Exception("Network error")

        request = market_data_pb2.GetBatchOHLCVRequest(
            symbols=["AAPL"],
            interval="1d",
            period="1mo",
        )

        with pytest.raises(grpc.RpcError):
            await servicer.GetBatchOHLCV(request, mock_context)

        mock_context.abort.assert_called_once()


class TestSyncSymbol(TestMarketDataServicer):
    """Tests for SyncSymbol RPC."""

    @pytest.mark.asyncio
    async def test_sync_symbol_no_repository(
        self,
        servicer: MarketDataServicer,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with UNAVAILABLE when repository not configured."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.SyncSymbolRequest(
            symbol="AAPL",
            interval="1d",
        )

        with pytest.raises(grpc.RpcError):
            await servicer.SyncSymbol(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_sync_symbol_success(
        self,
        servicer_with_repo: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Should sync symbol successfully."""
        from shared.generated import market_data_pb2

        mock_fetcher.fetch_and_store_ohlcv = AsyncMock(return_value=100)
        mock_fetcher.sync_stock_info = AsyncMock(return_value=True)

        request = market_data_pb2.SyncSymbolRequest(
            symbol="aapl",
            interval="1d",
            full_refresh=False,
        )
        response = await servicer_with_repo.SyncSymbol(request, mock_context)

        assert response.symbol == "AAPL"
        assert response.bars_synced == 100
        assert response.stock_info_updated is True

    @pytest.mark.asyncio
    async def test_sync_symbol_value_error(
        self,
        servicer_with_repo: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with INVALID_ARGUMENT on ValueError."""
        from shared.generated import market_data_pb2

        mock_fetcher.fetch_and_store_ohlcv = AsyncMock(
            side_effect=ValueError("Invalid symbol")
        )

        request = market_data_pb2.SyncSymbolRequest(
            symbol="INVALID",
            interval="1d",
        )

        with pytest.raises(grpc.RpcError):
            await servicer_with_repo.SyncSymbol(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INVALID_ARGUMENT

    @pytest.mark.asyncio
    async def test_sync_symbol_internal_error(
        self,
        servicer_with_repo: MarketDataServicer,
        mock_fetcher: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with INTERNAL on unexpected error."""
        from shared.generated import market_data_pb2

        mock_fetcher.fetch_and_store_ohlcv = AsyncMock(
            side_effect=Exception("Database error")
        )

        request = market_data_pb2.SyncSymbolRequest(
            symbol="AAPL",
            interval="1d",
        )

        with pytest.raises(grpc.RpcError):
            await servicer_with_repo.SyncSymbol(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INTERNAL


class TestListSymbols(TestMarketDataServicer):
    """Tests for ListSymbols RPC."""

    @pytest.mark.asyncio
    async def test_list_symbols_no_repository(
        self,
        servicer: MarketDataServicer,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with UNAVAILABLE when repository not configured."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.ListSymbolsRequest()

        with pytest.raises(grpc.RpcError):
            await servicer.ListSymbols(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_list_symbols_success(
        self,
        servicer_with_repo: MarketDataServicer,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should list symbols successfully."""
        from shared.generated import market_data_pb2

        mock_repository.list_symbols.return_value = (["AAPL", "MSFT", "GOOGL"], 100)

        request = market_data_pb2.ListSymbolsRequest()
        response = await servicer_with_repo.ListSymbols(request, mock_context)

        assert list(response.symbols) == ["AAPL", "MSFT", "GOOGL"]
        assert response.total == 100

    @pytest.mark.asyncio
    async def test_list_symbols_with_sector(
        self,
        servicer_with_repo: MarketDataServicer,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should filter by sector."""
        from shared.generated import market_data_pb2

        mock_repository.list_symbols.return_value = (["AAPL", "MSFT"], 2)

        request = market_data_pb2.ListSymbolsRequest(
            sector="Technology",
            limit=50,
        )
        response = await servicer_with_repo.ListSymbols(request, mock_context)

        assert list(response.symbols) == ["AAPL", "MSFT"]
        mock_repository.list_symbols.assert_called_once_with(
            sector="Technology",
            limit=50,
        )

    @pytest.mark.asyncio
    async def test_list_symbols_internal_error(
        self,
        servicer_with_repo: MarketDataServicer,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should abort with INTERNAL on error."""
        from shared.generated import market_data_pb2

        mock_repository.list_symbols.side_effect = Exception("Database error")

        request = market_data_pb2.ListSymbolsRequest()

        with pytest.raises(grpc.RpcError):
            await servicer_with_repo.ListSymbols(request, mock_context)

        mock_context.abort.assert_called_once()


class TestServicerInitialization(TestMarketDataServicer):
    """Tests for servicer initialization."""

    def test_init_with_all_dependencies(
        self,
        mock_redis: AsyncMock,
        mock_fetcher: MagicMock,
        mock_repository: AsyncMock,
    ) -> None:
        """Should initialize with all dependencies."""
        servicer = MarketDataServicer(
            redis_client=mock_redis,
            data_fetcher=mock_fetcher,
            repository=mock_repository,
            cache_ttl=600,
        )

        assert servicer.redis == mock_redis
        assert servicer.fetcher == mock_fetcher
        assert servicer.repository == mock_repository
        assert servicer.cache_ttl == 600

    def test_init_with_default_fetcher(
        self,
        mock_redis: AsyncMock,
    ) -> None:
        """Should create default fetcher when not provided."""
        servicer = MarketDataServicer(
            redis_client=mock_redis,
            data_fetcher=None,
        )

        assert servicer.fetcher is not None
        assert isinstance(servicer.fetcher, MarketDataFetcher)

    def test_init_with_minimal_dependencies(self) -> None:
        """Should work with minimal dependencies."""
        servicer = MarketDataServicer()

        assert servicer.redis is None
        assert servicer.repository is None
        assert servicer.fetcher is not None
        assert servicer.cache_ttl == 300
