"""Tests for gRPC clients."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import grpc


class TestClassificationClient:
    """Tests for ClassificationClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create mock gRPC stub."""
        return AsyncMock()

    @pytest.fixture
    def client(self):
        """Create ClassificationClient instance."""
        from src.clients.classification_client import ClassificationClient
        return ClassificationClient(host="localhost", port=50051)

    @pytest.mark.asyncio
    async def test_init(self, client):
        """Test client initialization."""
        assert client.host == "localhost"
        assert client.port == 50051
        assert client.address == "localhost:50051"
        assert client.channel is None
        assert client.stub is None

    @pytest.mark.asyncio
    async def test_connect_success(self, client):
        """Test successful connection."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            await client.connect()
            assert client.channel is not None
            assert client.stub is not None
            mock_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, client):
        """Test connect when already connected."""
        client.channel = MagicMock()
        client.stub = MagicMock()

        with patch("grpc.aio.insecure_channel") as mock_channel:
            await client.connect()
            mock_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_candidate_symbols_success(self, client, mock_stub):
        """Test successful candidate symbols retrieval."""
        # Setup mock response
        mock_candidate = MagicMock()
        mock_candidate.symbol = "AAPL"
        mock_candidate.sector = "Technology"
        mock_candidate.theme = "AI"
        mock_candidate.preliminary_score = 85.0

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.selected_sectors = ["Technology"]
        mock_response.top_themes = ["AI"]

        mock_stub.GetCandidateSymbols = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        candidates, sectors, themes = await client.get_candidate_symbols("bull")

        assert len(candidates) == 1
        assert candidates[0].symbol == "AAPL"
        assert sectors == ["Technology"]
        assert themes == ["AI"]

    @pytest.mark.asyncio
    async def test_get_candidate_symbols_unavailable(self, client, mock_stub):
        """Test handling of unavailable service."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string=None,
        )
        mock_stub.GetCandidateSymbols = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(ConnectionError):
            await client.get_candidate_symbols("bull")

    @pytest.mark.asyncio
    async def test_get_candidate_symbols_timeout(self, client, mock_stub):
        """Test handling of timeout."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.DEADLINE_EXCEEDED,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Deadline exceeded",
            debug_error_string=None,
        )
        mock_stub.GetCandidateSymbols = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(TimeoutError):
            await client.get_candidate_symbols("bull")

    @pytest.mark.asyncio
    async def test_get_sector_analysis_success(self, client, mock_stub):
        """Test successful sector analysis retrieval."""
        mock_response = MagicMock()
        mock_stub.GetSectorAnalysis = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        response = await client.get_sector_analysis("bull")
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_get_sector_analysis_unavailable(self, client, mock_stub):
        """Test handling of unavailable service for sector analysis."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string=None,
        )
        mock_stub.GetSectorAnalysis = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(ConnectionError):
            await client.get_sector_analysis("bull")

    @pytest.mark.asyncio
    async def test_get_sector_analysis_timeout(self, client, mock_stub):
        """Test handling of timeout for sector analysis."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.DEADLINE_EXCEEDED,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Deadline exceeded",
            debug_error_string=None,
        )
        mock_stub.GetSectorAnalysis = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(TimeoutError):
            await client.get_sector_analysis("bull")

    @pytest.mark.asyncio
    async def test_get_thematic_analysis_success(self, client, mock_stub):
        """Test successful thematic analysis retrieval."""
        mock_response = MagicMock()
        mock_stub.GetThematicAnalysis = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        response = await client.get_thematic_analysis(["Technology"], "bull")
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_get_thematic_analysis_unavailable(self, client, mock_stub):
        """Test handling of unavailable service for thematic analysis."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string=None,
        )
        mock_stub.GetThematicAnalysis = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(ConnectionError):
            await client.get_thematic_analysis(["Technology"], "bull")

    @pytest.mark.asyncio
    async def test_get_thematic_analysis_timeout(self, client, mock_stub):
        """Test handling of timeout for thematic analysis."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.DEADLINE_EXCEEDED,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Deadline exceeded",
            debug_error_string=None,
        )
        mock_stub.GetThematicAnalysis = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(TimeoutError):
            await client.get_thematic_analysis(["Technology"], "bull")

    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test client close."""
        mock_channel = AsyncMock()
        client.channel = mock_channel
        client.stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client.channel is None
        assert client.stub is None

    @pytest.mark.asyncio
    async def test_close_not_connected(self, client):
        """Test close when not connected."""
        await client.close()  # Should not raise


class TestMarketRegimeClient:
    """Tests for MarketRegimeClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create mock gRPC stub."""
        return AsyncMock()

    @pytest.fixture
    def client(self):
        """Create MarketRegimeClient instance."""
        from src.clients.market_regime_client import MarketRegimeClient
        return MarketRegimeClient(host="localhost", port=50052)

    @pytest.mark.asyncio
    async def test_init(self, client):
        """Test client initialization."""
        assert client.host == "localhost"
        assert client.port == 50052
        assert client.address == "localhost:50052"

    @pytest.mark.asyncio
    async def test_connect_success(self, client):
        """Test successful connection."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            await client.connect()
            assert client.channel is not None
            assert client.stub is not None

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, client):
        """Test connect when already connected."""
        client.channel = MagicMock()
        client.stub = MagicMock()

        with patch("grpc.aio.insecure_channel") as mock_channel:
            await client.connect()
            mock_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_current_regime_success(self, client, mock_stub):
        """Test successful regime retrieval."""
        mock_response = MagicMock()
        mock_response.regime = "bull"
        mock_response.confidence = 0.85
        mock_stub.GetCurrentRegime = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        response = await client.get_current_regime()

        assert response.regime == "bull"
        assert response.confidence == 0.85

    @pytest.mark.asyncio
    async def test_get_current_regime_unavailable(self, client, mock_stub):
        """Test handling of unavailable service."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string=None,
        )
        mock_stub.GetCurrentRegime = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(ConnectionError):
            await client.get_current_regime()

    @pytest.mark.asyncio
    async def test_get_current_regime_timeout(self, client, mock_stub):
        """Test handling of timeout."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.DEADLINE_EXCEEDED,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Deadline exceeded",
            debug_error_string=None,
        )
        mock_stub.GetCurrentRegime = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(TimeoutError):
            await client.get_current_regime()

    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test client close."""
        mock_channel = AsyncMock()
        client.channel = mock_channel
        client.stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client.channel is None

    @pytest.mark.asyncio
    async def test_close_not_connected(self, client):
        """Test close when not connected."""
        await client.close()  # Should not raise


class TestMarketDataClient:
    """Tests for MarketDataClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create mock gRPC stub."""
        return AsyncMock()

    @pytest.fixture
    def client(self):
        """Create MarketDataClient instance."""
        from src.clients.market_data_client import MarketDataClient
        return MarketDataClient(host="localhost", port=50053)

    @pytest.mark.asyncio
    async def test_init(self, client):
        """Test client initialization."""
        assert client.host == "localhost"
        assert client.port == 50053
        assert client.address == "localhost:50053"

    @pytest.mark.asyncio
    async def test_connect_success(self, client):
        """Test successful connection."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            await client.connect()
            assert client.channel is not None
            assert client.stub is not None

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, client):
        """Test connect when already connected."""
        client.channel = MagicMock()
        client.stub = MagicMock()

        with patch("grpc.aio.insecure_channel") as mock_channel:
            await client.connect()
            mock_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_ohlcv_success(self, client, mock_stub):
        """Test successful OHLCV data retrieval."""
        mock_bar = MagicMock()
        mock_bar.timestamp = "2024-01-15T09:30:00Z"
        mock_bar.open = 150.0
        mock_bar.high = 152.0
        mock_bar.low = 149.0
        mock_bar.close = 151.5
        mock_bar.volume = 1000000
        mock_bar.HasField.return_value = True
        mock_bar.adj_close = 151.5

        mock_response = MagicMock()
        mock_response.bars = [mock_bar]
        mock_stub.GetOHLCV = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        data = await client.get_ohlcv("AAPL", period="3mo", interval="1d")

        assert len(data) == 1
        assert data[0]["close"] == 151.5
        assert data[0]["volume"] == 1000000

    @pytest.mark.asyncio
    async def test_get_ohlcv_unavailable(self, client, mock_stub):
        """Test handling of unavailable service."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string=None,
        )
        mock_stub.GetOHLCV = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(ConnectionError):
            await client.get_ohlcv("AAPL")

    @pytest.mark.asyncio
    async def test_get_ohlcv_timeout(self, client, mock_stub):
        """Test handling of timeout."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.DEADLINE_EXCEEDED,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Deadline exceeded",
            debug_error_string=None,
        )
        mock_stub.GetOHLCV = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(TimeoutError):
            await client.get_ohlcv("AAPL")

    @pytest.mark.asyncio
    async def test_get_stock_info_success(self, client, mock_stub):
        """Test successful stock info retrieval."""
        mock_response = MagicMock()
        mock_response.symbol = "AAPL"
        mock_response.name = "Apple Inc."
        mock_stub.GetStockInfo = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        response = await client.get_stock_info("AAPL")
        assert response.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_stock_info_unavailable(self, client, mock_stub):
        """Test handling of unavailable service for stock info."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string=None,
        )
        mock_stub.GetStockInfo = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(ConnectionError):
            await client.get_stock_info("AAPL")

    @pytest.mark.asyncio
    async def test_get_stock_info_timeout(self, client, mock_stub):
        """Test handling of timeout for stock info."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.DEADLINE_EXCEEDED,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Deadline exceeded",
            debug_error_string=None,
        )
        mock_stub.GetStockInfo = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(TimeoutError):
            await client.get_stock_info("AAPL")

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_success(self, client, mock_stub):
        """Test successful batch OHLCV data retrieval."""
        mock_bar = MagicMock()
        mock_bar.timestamp = "2024-01-15T09:30:00Z"
        mock_bar.open = 150.0
        mock_bar.high = 152.0
        mock_bar.low = 149.0
        mock_bar.close = 151.5
        mock_bar.volume = 1000000
        mock_bar.HasField.return_value = False

        mock_ohlcv_response = MagicMock()
        mock_ohlcv_response.bars = [mock_bar]

        mock_response = MagicMock()
        mock_response.data = {"AAPL": mock_ohlcv_response}
        mock_stub.GetBatchOHLCV = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        data = await client.get_batch_ohlcv(["AAPL"])

        assert "AAPL" in data
        assert len(data["AAPL"]) == 1
        assert data["AAPL"][0]["close"] == 151.5

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_unavailable(self, client, mock_stub):
        """Test handling of unavailable service for batch OHLCV."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string=None,
        )
        mock_stub.GetBatchOHLCV = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(ConnectionError):
            await client.get_batch_ohlcv(["AAPL"])

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_timeout(self, client, mock_stub):
        """Test handling of timeout for batch OHLCV."""
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.DEADLINE_EXCEEDED,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Deadline exceeded",
            debug_error_string=None,
        )
        mock_stub.GetBatchOHLCV = AsyncMock(side_effect=error)
        client.stub = mock_stub

        with pytest.raises(TimeoutError):
            await client.get_batch_ohlcv(["AAPL"])

    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test client close."""
        mock_channel = AsyncMock()
        client.channel = mock_channel
        client.stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client.channel is None

    @pytest.mark.asyncio
    async def test_close_not_connected(self, client):
        """Test close when not connected."""
        await client.close()  # Should not raise
