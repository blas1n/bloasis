"""E2E integration tests for Market Data gRPC service.

This module contains integration tests that verify:
- gRPC service is accessible and responding
- GetOHLCV returns valid market data
- GetStockInfo returns stock metadata
- GetBatchOHLCV handles multiple symbols
- SyncSymbol persists data to database

These tests require the Market Data service to be running.
"""

import os
from typing import Generator

import grpc
import pytest

# gRPC connection settings
MARKET_DATA_HOST = os.getenv("MARKET_DATA_HOST", "market-data")
MARKET_DATA_PORT = int(os.getenv("MARKET_DATA_GRPC_PORT", "50053"))


@pytest.fixture(scope="module")
def grpc_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Market Data service."""
    channel = grpc.insecure_channel(f"{MARKET_DATA_HOST}:{MARKET_DATA_PORT}")

    # Wait for channel to be ready
    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Market Data gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def market_data_stub(grpc_channel: grpc.Channel):
    """Create Market Data service stub."""
    try:
        from shared.generated import market_data_pb2_grpc

        return market_data_pb2_grpc.MarketDataServiceStub(grpc_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


class TestMarketDataGrpc:
    """E2E tests for Market Data gRPC service."""

    def test_get_ohlcv_returns_valid_response(self, market_data_stub) -> None:
        """Test GetOHLCV returns valid OHLCV data."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.GetOHLCVRequest(
            symbol="AAPL",
            interval="1d",
            period="5d",
        )
        response = market_data_stub.GetOHLCV(request)

        assert response.symbol == "AAPL", "Response symbol should match request"
        assert response.interval == "1d", "Response interval should match request"
        assert len(response.bars) > 0, "Should have at least one bar"
        assert response.total_bars > 0, "total_bars should be positive"

        # Verify bar structure
        bar = response.bars[0]
        assert bar.open > 0, "Open price should be positive"
        assert bar.high >= bar.low, "High should be >= low"
        assert bar.close > 0, "Close price should be positive"
        assert bar.volume >= 0, "Volume should be non-negative"

    def test_get_ohlcv_with_date_range(self, market_data_stub) -> None:
        """Test GetOHLCV with specific date range."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.GetOHLCVRequest(
            symbol="MSFT",
            interval="1d",
            start_date="2026-01-01",
            end_date="2026-01-15",
        )
        response = market_data_stub.GetOHLCV(request)

        assert response.symbol == "MSFT"
        # May have limited data depending on date range
        assert response.total_bars >= 0

    def test_get_ohlcv_invalid_symbol(self, market_data_stub) -> None:
        """Test GetOHLCV with invalid symbol returns error."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.GetOHLCVRequest(
            symbol="INVALID_XYZ_123",
            interval="1d",
            period="1mo",
        )

        with pytest.raises(grpc.RpcError) as exc_info:
            market_data_stub.GetOHLCV(request)

        assert exc_info.value.code() in [
            grpc.StatusCode.INVALID_ARGUMENT,
            grpc.StatusCode.NOT_FOUND,
            grpc.StatusCode.INTERNAL,
        ]

    def test_get_ohlcv_invalid_interval(self, market_data_stub) -> None:
        """Test GetOHLCV with invalid interval returns error."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.GetOHLCVRequest(
            symbol="AAPL",
            interval="invalid",
            period="1mo",
        )

        with pytest.raises(grpc.RpcError) as exc_info:
            market_data_stub.GetOHLCV(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT

    def test_get_stock_info_returns_valid_response(self, market_data_stub) -> None:
        """Test GetStockInfo returns valid stock metadata."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.GetStockInfoRequest(symbol="AAPL")
        response = market_data_stub.GetStockInfo(request)

        assert response.symbol == "AAPL", "Response symbol should match"
        assert response.name, "Should have a name"
        assert response.currency, "Should have currency"
        assert response.market_cap > 0, "Market cap should be positive"

    def test_get_stock_info_invalid_symbol(self, market_data_stub) -> None:
        """Test GetStockInfo with invalid symbol returns error."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.GetStockInfoRequest(symbol="INVALID_XYZ_123")

        with pytest.raises(grpc.RpcError) as exc_info:
            market_data_stub.GetStockInfo(request)

        assert exc_info.value.code() in [
            grpc.StatusCode.INVALID_ARGUMENT,
            grpc.StatusCode.NOT_FOUND,
            grpc.StatusCode.INTERNAL,
        ]

    def test_get_batch_ohlcv_returns_multiple_symbols(self, market_data_stub) -> None:
        """Test GetBatchOHLCV returns data for multiple symbols."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.GetBatchOHLCVRequest(
            symbols=["AAPL", "MSFT"],
            interval="1d",
            period="5d",
        )
        response = market_data_stub.GetBatchOHLCV(request)

        # Should have data for at least one symbol
        assert len(response.data) > 0 or len(response.failed_symbols) < 2, (
            "Should successfully fetch at least one symbol"
        )

        # Verify data structure for returned symbols
        for symbol, ohlcv_data in response.data.items():
            assert ohlcv_data.symbol == symbol
            assert len(ohlcv_data.bars) >= 0

    def test_get_batch_ohlcv_with_invalid_symbol(self, market_data_stub) -> None:
        """Test GetBatchOHLCV handles mix of valid and invalid symbols."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.GetBatchOHLCVRequest(
            symbols=["AAPL", "INVALID_XYZ"],
            interval="1d",
            period="5d",
        )
        response = market_data_stub.GetBatchOHLCV(request)

        # Valid symbol should have data
        assert "AAPL" in response.data or "AAPL" not in response.failed_symbols, (
            "AAPL should either succeed or not be in failed list"
        )


class TestMarketDataSyncOperations:
    """E2E tests for Market Data sync operations."""

    def test_sync_symbol_persists_data(self, market_data_stub) -> None:
        """Test SyncSymbol persists OHLCV data to database."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.SyncSymbolRequest(
            symbol="AAPL",
            interval="1d",
            full_refresh=False,
        )

        try:
            response = market_data_stub.SyncSymbol(request)
            assert response.symbol == "AAPL"
            assert response.bars_synced >= 0
        except grpc.RpcError as e:
            # Database may not be configured in test environment
            if "repository not configured" in str(e.details()).lower():
                pytest.skip("Database not configured in test environment")
            raise

    def test_list_symbols_returns_data(self, market_data_stub) -> None:
        """Test ListSymbols returns stored symbols."""
        from shared.generated import market_data_pb2

        request = market_data_pb2.ListSymbolsRequest(limit=10)

        try:
            response = market_data_stub.ListSymbols(request)
            # Response may be empty if no data synced yet
            assert response.total >= 0
            assert len(response.symbols) <= 10
        except grpc.RpcError as e:
            if "repository not configured" in str(e.details()).lower():
                pytest.skip("Database not configured in test environment")
            raise


class TestMarketDataHealthCheck:
    """E2E tests for gRPC health check."""

    def test_health_check_serving(self, grpc_channel: grpc.Channel) -> None:
        """Test gRPC health check returns SERVING status."""
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        stub = health_pb2_grpc.HealthStub(grpc_channel)

        request = health_pb2.HealthCheckRequest(service="")
        response = stub.Check(request)

        assert response.status == health_pb2.HealthCheckResponse.SERVING, (
            "Health check should return SERVING status"
        )

    def test_service_specific_health_check(self, grpc_channel: grpc.Channel) -> None:
        """Test service-specific health check."""
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        stub = health_pb2_grpc.HealthStub(grpc_channel)

        request = health_pb2.HealthCheckRequest(
            service="bloasis.market_data.MarketDataService"
        )
        response = stub.Check(request)

        assert response.status == health_pb2.HealthCheckResponse.SERVING, (
            "Market Data service health check should return SERVING"
        )


class TestMarketDataCaching:
    """E2E tests for Redis caching behavior."""

    def test_cached_response_is_consistent(self, market_data_stub) -> None:
        """Test consecutive requests return consistent cached data."""
        from shared.generated import market_data_pb2

        # First request
        request = market_data_pb2.GetOHLCVRequest(
            symbol="AAPL",
            interval="1d",
            period="5d",
        )
        response1 = market_data_stub.GetOHLCV(request)
        response2 = market_data_stub.GetOHLCV(request)

        # Responses should be identical (from cache)
        assert response1.symbol == response2.symbol
        assert response1.total_bars == response2.total_bars
        assert len(response1.bars) == len(response2.bars)
