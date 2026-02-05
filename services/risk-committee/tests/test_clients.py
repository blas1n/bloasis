"""Tests for gRPC clients."""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from src.clients.market_data_client import MarketDataClient
from src.clients.portfolio_client import PortfolioClient


class TestPortfolioClient:
    """Tests for PortfolioClient."""

    def test_init_with_defaults(self):
        """Test initialization with default config."""
        with patch("src.clients.portfolio_client.config") as mock_config:
            mock_config.portfolio_host = "localhost"
            mock_config.portfolio_port = 50060

            client = PortfolioClient()

            assert client.host == "localhost"
            assert client.port == 50060
            assert client.channel is None

    def test_init_with_custom_values(self):
        """Test initialization with custom host and port."""
        client = PortfolioClient(host="custom-host", port=9999)

        assert client.host == "custom-host"
        assert client.port == 9999

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connection establishment."""
        client = PortfolioClient(host="test-host", port=50060)

        with patch("src.clients.portfolio_client.grpc.aio.insecure_channel") as mock_channel:
            mock_channel_instance = MagicMock()
            mock_channel.return_value = mock_channel_instance

            await client.connect()

            mock_channel.assert_called_once()
            assert client.channel == mock_channel_instance

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Test connect when already connected."""
        client = PortfolioClient(host="test-host", port=50060)
        client.channel = MagicMock()

        with patch("src.clients.portfolio_client.logger") as mock_logger:
            await client.connect()
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_positions(self):
        """Test getting portfolio positions."""
        client = PortfolioClient(host="test-host", port=50060)

        portfolio = await client.get_positions("test-user")

        assert portfolio.user_id == "test-user"
        assert portfolio.total_value == 100000.0
        assert len(portfolio.positions) == 2

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing connection."""
        client = PortfolioClient(host="test-host", port=50060)
        mock_channel = AsyncMock()
        client.channel = mock_channel

        await client.close()

        mock_channel.close.assert_called_once()
        assert client.channel is None


class TestMarketDataClient:
    """Tests for MarketDataClient."""

    def test_init_with_defaults(self):
        """Test initialization with default config."""
        with patch("src.clients.market_data_client.config") as mock_config:
            mock_config.market_data_host = "localhost"
            mock_config.market_data_port = 50052

            client = MarketDataClient()

            assert client.host == "localhost"
            assert client.port == 50052
            assert client.channel is None

    def test_init_with_custom_values(self):
        """Test initialization with custom host and port."""
        client = MarketDataClient(host="custom-host", port=9999)

        assert client.host == "custom-host"
        assert client.port == 9999

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connection establishment."""
        client = MarketDataClient(host="test-host", port=50052)

        with patch("src.clients.market_data_client.grpc.aio.insecure_channel") as mock_channel:
            mock_channel_instance = MagicMock()
            mock_channel.return_value = mock_channel_instance

            with patch(
                "src.clients.market_data_client.market_data_pb2_grpc.MarketDataServiceStub"
            ) as mock_stub:
                await client.connect()

                mock_channel.assert_called_once()
                mock_stub.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Test connect when already connected."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()

        with patch("src.clients.market_data_client.logger") as mock_logger:
            await client.connect()
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_vix_success(self):
        """Test getting VIX successfully."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        mock_bar = MagicMock()
        mock_bar.close = 25.5
        mock_response = MagicMock()
        mock_response.bars = [mock_bar]

        client.stub.GetOHLCV = AsyncMock(return_value=mock_response)

        vix = await client.get_vix()

        assert vix == 25.5

    @pytest.mark.asyncio
    async def test_get_vix_empty_bars(self):
        """Test getting VIX with empty bars returns default."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        mock_response = MagicMock()
        mock_response.bars = []

        client.stub.GetOHLCV = AsyncMock(return_value=mock_response)

        vix = await client.get_vix()

        assert vix == 20.0  # Default

    @pytest.mark.asyncio
    async def test_get_vix_unavailable_error(self):
        """Test getting VIX with unavailable service."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        error.details = MagicMock(return_value="Service unavailable")

        client.stub.GetOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(ConnectionError):
            await client.get_vix()

    @pytest.mark.asyncio
    async def test_get_vix_timeout_error(self):
        """Test getting VIX with timeout."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.DEADLINE_EXCEEDED)
        error.details = MagicMock(return_value="Deadline exceeded")

        client.stub.GetOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(TimeoutError):
            await client.get_vix()

    @pytest.mark.asyncio
    async def test_get_average_volume_success(self):
        """Test getting average volume successfully."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        mock_bars = [MagicMock(volume=1000000), MagicMock(volume=2000000)]
        mock_response = MagicMock()
        mock_response.bars = mock_bars

        client.stub.GetOHLCV = AsyncMock(return_value=mock_response)

        avg_volume = await client.get_average_volume("AAPL")

        assert avg_volume == 1500000.0

    @pytest.mark.asyncio
    async def test_get_average_volume_empty_bars(self):
        """Test getting average volume with empty bars."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        mock_response = MagicMock()
        mock_response.bars = []

        client.stub.GetOHLCV = AsyncMock(return_value=mock_response)

        avg_volume = await client.get_average_volume("AAPL")

        assert avg_volume == 0.0

    @pytest.mark.asyncio
    async def test_get_average_volume_unavailable_error(self):
        """Test getting volume with unavailable service."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        error.details = MagicMock(return_value="Service unavailable")

        client.stub.GetOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(ConnectionError):
            await client.get_average_volume("AAPL")

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing connection."""
        client = MarketDataClient(host="test-host", port=50052)
        mock_channel = AsyncMock()
        client.channel = mock_channel
        client.stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client.channel is None
        assert client.stub is None

    @pytest.mark.asyncio
    async def test_close_not_connected(self):
        """Test closing when not connected."""
        client = MarketDataClient(host="test-host", port=50052)

        # Should not raise
        await client.close()

        assert client.channel is None
