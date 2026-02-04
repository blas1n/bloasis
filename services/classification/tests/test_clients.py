"""Unit tests for client modules."""

from unittest.mock import AsyncMock, patch

import grpc
import pytest
from shared.generated import market_regime_pb2

from src.clients.fingpt_client import FinGPTClient, MockFinGPTClient
from src.clients.market_regime_client import MarketRegimeClient


@pytest.mark.asyncio
class TestFinGPTClient:
    """Test real FinGPTClient wrapper."""

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        client = FinGPTClient(api_key="test_key", model="test_model")
        # Verify the client was initialized (wrapper uses internal _client)
        assert client._client is not None

    def test_init_without_api_key(self):
        """Test initialization without API key raises error."""
        with pytest.raises(ValueError, match="Hugging Face API token required"):
            FinGPTClient(api_key="", model="test_model")

    async def test_close(self):
        """Test closing HTTP client."""
        client = FinGPTClient(api_key="test_key")
        await client.close()  # Should not raise


@pytest.mark.asyncio
class TestMockFinGPTClient:
    """Test MockFinGPTClient."""

    async def test_analyze_sectors_bull(self):
        """Test sector analysis for bull regime."""
        client = MockFinGPTClient()
        sectors = await client.analyze_sectors("bull")

        assert len(sectors) == 11  # All GICS sectors
        assert all(s.sector for s in sectors)
        assert all(0 <= s.score <= 100 for s in sectors)

        # Bull regime should select growth sectors
        selected = [s.sector for s in sectors if s.selected]
        assert "Technology" in selected

    async def test_analyze_sectors_crisis(self):
        """Test sector analysis for crisis regime."""
        client = MockFinGPTClient()
        sectors = await client.analyze_sectors("crisis")

        # Crisis regime should select defensive sectors
        selected = [s.sector for s in sectors if s.selected]
        defensive = {"Utilities", "Consumer Staples", "Healthcare"}
        assert any(s in defensive for s in selected)

    async def test_analyze_themes(self):
        """Test thematic analysis."""
        client = MockFinGPTClient()
        themes = await client.analyze_themes(["Technology", "Healthcare"], "bull")

        assert len(themes) > 0
        assert all(t.theme for t in themes)
        assert all(t.sector in ["Technology", "Healthcare"] for t in themes)
        assert all(len(t.representative_symbols) > 0 for t in themes)

    async def test_close(self):
        """Test close is a no-op."""
        client = MockFinGPTClient()
        await client.close()  # Should not raise


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
