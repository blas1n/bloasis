"""Unit tests for client modules."""

from unittest.mock import AsyncMock, patch

import grpc
import pytest
from shared.generated import market_regime_pb2

from src.clients.market_regime_client import MarketRegimeClient


@pytest.mark.asyncio
class TestMarketRegimeClient:
    """Test MarketRegimeClient."""

    async def test_connect(self):
        """Test connection."""
        client = MarketRegimeClient()
        await client.connect()

        assert client.channel is not None
        assert client.stub is not None

        await client.close()

    async def test_get_current_regime_success(self):
        """Test successful regime fetch."""
        client = MarketRegimeClient()

        # Mock the gRPC stub
        with patch.object(client, "stub", create=True) as mock_stub:
            mock_response = market_regime_pb2.GetCurrentRegimeResponse(
                regime="bull",
                confidence=0.85,
                timestamp="2026-02-02T12:00:00Z",
                trigger="baseline",
            )
            mock_stub.GetCurrentRegime = AsyncMock(return_value=mock_response)

            response = await client.get_current_regime()

            assert response.regime == "bull"
            assert response.confidence == 0.85

    async def test_get_current_regime_force_refresh(self):
        """Test regime fetch with force_refresh."""
        client = MarketRegimeClient()

        with patch.object(client, "stub", create=True) as mock_stub:
            mock_response = market_regime_pb2.GetCurrentRegimeResponse(
                regime="bear",
                confidence=0.90,
                timestamp="2026-02-02T12:00:00Z",
                trigger="baseline",
            )
            mock_stub.GetCurrentRegime = AsyncMock(return_value=mock_response)

            response = await client.get_current_regime(force_refresh=True)

            assert response.regime == "bear"
            # Verify force_refresh was passed
            call_args = mock_stub.GetCurrentRegime.call_args
            assert call_args[0][0].force_refresh is True

    async def test_get_current_regime_unavailable(self):
        """Test handling when service is unavailable."""
        client = MarketRegimeClient()

        with patch.object(client, "stub", create=True) as mock_stub:
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.UNAVAILABLE
            error.details = lambda: "Service unavailable"
            mock_stub.GetCurrentRegime = AsyncMock(side_effect=error)

            with pytest.raises(ConnectionError):
                await client.get_current_regime()

    async def test_get_current_regime_timeout(self):
        """Test handling when service times out."""
        client = MarketRegimeClient()

        with patch.object(client, "stub", create=True) as mock_stub:
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.DEADLINE_EXCEEDED
            error.details = lambda: "Timeout"
            mock_stub.GetCurrentRegime = AsyncMock(side_effect=error)

            with pytest.raises(TimeoutError):
                await client.get_current_regime()

    async def test_close(self):
        """Test closing connection."""
        client = MarketRegimeClient()
        await client.connect()
        await client.close()

        assert client.channel is None
        assert client.stub is None
