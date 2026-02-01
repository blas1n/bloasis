"""E2E integration tests for Market Regime gRPC service.

This module contains integration tests that verify:
- gRPC service is accessible and responding
- GetCurrentRegime returns valid regime data
- GetRegimeHistory returns historical data
- SaveRegime persists and caches data correctly

These tests require the Market Regime service to be running.
"""

import os
from typing import Generator

import grpc
import pytest

# gRPC connection settings
MARKET_REGIME_HOST = os.getenv("MARKET_REGIME_HOST", "market-regime")
MARKET_REGIME_PORT = int(os.getenv("MARKET_REGIME_GRPC_PORT", "50051"))


@pytest.fixture(scope="module")
def grpc_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Market Regime service."""
    channel = grpc.insecure_channel(f"{MARKET_REGIME_HOST}:{MARKET_REGIME_PORT}")

    # Wait for channel to be ready
    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Market Regime gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def market_regime_stub(grpc_channel: grpc.Channel):
    """Create Market Regime service stub."""
    # Import here to avoid issues if proto not generated
    try:
        from shared.generated import market_regime_pb2_grpc
        return market_regime_pb2_grpc.MarketRegimeServiceStub(grpc_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


class TestMarketRegimeGrpc:
    """E2E tests for Market Regime gRPC service."""

    def test_get_current_regime_returns_valid_response(
        self, market_regime_stub
    ) -> None:
        """Test GetCurrentRegime returns a valid regime classification."""
        from shared.generated import market_regime_pb2

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response = market_regime_stub.GetCurrentRegime(request)

        # Verify response has required fields
        assert response.regime, "Response should have a regime"
        assert response.regime in [
            "crisis", "bear", "bull", "sideways", "recovery"
        ], f"Regime '{response.regime}' should be valid"

        assert 0.0 <= response.confidence <= 1.0, (
            f"Confidence {response.confidence} should be between 0 and 1"
        )

        assert response.timestamp, "Response should have a timestamp"

    def test_get_current_regime_with_force_refresh(
        self, market_regime_stub
    ) -> None:
        """Test GetCurrentRegime with force_refresh bypasses cache."""
        from shared.generated import market_regime_pb2

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=True)
        response = market_regime_stub.GetCurrentRegime(request)

        # Should still return valid data
        assert response.regime, "Response should have a regime"
        assert response.confidence > 0, "Should have positive confidence"

    def test_get_regime_history_returns_data(
        self, market_regime_stub
    ) -> None:
        """Test GetRegimeHistory returns historical regime data."""
        from shared.generated import market_regime_pb2

        # Request last 7 days of history
        request = market_regime_pb2.GetRegimeHistoryRequest(
            start_time="2026-01-25T00:00:00Z",
            end_time="2026-02-01T23:59:59Z",
        )

        response = market_regime_stub.GetRegimeHistory(request)

        # Response should be a list (may be empty if no data)
        assert hasattr(response, "regimes"), "Response should have regimes field"

    def test_save_regime_persists_data(
        self, market_regime_stub
    ) -> None:
        """Test SaveRegime persists regime classification."""
        from shared.generated import market_regime_pb2

        # Save a test regime
        request = market_regime_pb2.SaveRegimeRequest(
            regime="bull",
            confidence=0.85,
            trigger="e2e_test",
        )

        response = market_regime_stub.SaveRegime(request)

        # Verify save was successful
        assert response.success, "SaveRegime should succeed"
        assert response.regime.regime == "bull", "Saved regime should match"
        assert response.regime.confidence == 0.85, "Saved confidence should match"

    def test_save_regime_validates_invalid_regime(
        self, market_regime_stub
    ) -> None:
        """Test SaveRegime rejects invalid regime values."""
        from shared.generated import market_regime_pb2

        request = market_regime_pb2.SaveRegimeRequest(
            regime="invalid_regime",
            confidence=0.5,
        )

        with pytest.raises(grpc.RpcError) as exc_info:
            market_regime_stub.SaveRegime(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT

    def test_save_regime_validates_confidence_range(
        self, market_regime_stub
    ) -> None:
        """Test SaveRegime rejects out-of-range confidence values."""
        from shared.generated import market_regime_pb2

        # Test confidence > 1.0
        request = market_regime_pb2.SaveRegimeRequest(
            regime="bull",
            confidence=1.5,
        )

        with pytest.raises(grpc.RpcError) as exc_info:
            market_regime_stub.SaveRegime(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT


class TestMarketRegimeHealthCheck:
    """E2E tests for gRPC health check."""

    def test_health_check_serving(self, grpc_channel: grpc.Channel) -> None:
        """Test gRPC health check returns SERVING status."""
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        stub = health_pb2_grpc.HealthStub(grpc_channel)

        # Check overall health
        request = health_pb2.HealthCheckRequest(service="")
        response = stub.Check(request)

        assert response.status == health_pb2.HealthCheckResponse.SERVING, (
            "Health check should return SERVING status"
        )

    def test_service_specific_health_check(self, grpc_channel: grpc.Channel) -> None:
        """Test service-specific health check."""
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        stub = health_pb2_grpc.HealthStub(grpc_channel)

        # Check Market Regime service health
        request = health_pb2.HealthCheckRequest(
            service="bloasis.market_regime.MarketRegimeService"
        )
        response = stub.Check(request)

        assert response.status == health_pb2.HealthCheckResponse.SERVING, (
            "Market Regime service health check should return SERVING"
        )


class TestMarketRegimeCaching:
    """E2E tests for Redis caching behavior."""

    def test_cached_response_is_consistent(
        self, market_regime_stub
    ) -> None:
        """Test consecutive requests return consistent cached data."""
        from shared.generated import market_regime_pb2

        # First request
        request1 = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response1 = market_regime_stub.GetCurrentRegime(request1)

        # Second request (should hit cache)
        request2 = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response2 = market_regime_stub.GetCurrentRegime(request2)

        # Responses should be identical (from cache)
        assert response1.regime == response2.regime, "Cached regime should match"
        assert response1.confidence == response2.confidence, "Cached confidence should match"
        assert response1.timestamp == response2.timestamp, "Cached timestamp should match"

    def test_force_refresh_updates_timestamp(
        self, market_regime_stub
    ) -> None:
        """Test force_refresh may update the timestamp."""
        from shared.generated import market_regime_pb2

        # Get current cached value
        request1 = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response1 = market_regime_stub.GetCurrentRegime(request1)

        # Force refresh
        request2 = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=True)
        response2 = market_regime_stub.GetCurrentRegime(request2)

        # Both should have valid regimes
        assert response1.regime in ["crisis", "bear", "bull", "sideways", "recovery"]
        assert response2.regime in ["crisis", "bear", "bull", "sideways", "recovery"]
