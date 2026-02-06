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
            assert client.stub is None

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

            with patch(
                "src.clients.portfolio_client.portfolio_pb2_grpc.PortfolioServiceStub"
            ) as mock_stub:
                await client.connect()

                mock_channel.assert_called_once()
                mock_stub.assert_called_once_with(mock_channel_instance)
                assert client.channel == mock_channel_instance
                assert client.stub is not None

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Test connect when already connected."""
        client = PortfolioClient(host="test-host", port=50060)
        client.channel = MagicMock()

        with patch("src.clients.portfolio_client.logger") as mock_logger:
            await client.connect()
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_positions_success(self):
        """Test getting portfolio positions successfully."""
        client = PortfolioClient(host="test-host", port=50060)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        # Create mock position with Money proto
        mock_position1 = MagicMock()
        mock_position1.symbol = "AAPL"
        mock_position1.quantity = 50
        mock_position1.current_value = MagicMock(amount="8750.00", currency="USD")

        mock_position2 = MagicMock()
        mock_position2.symbol = "GOOGL"
        mock_position2.quantity = 20
        mock_position2.current_value = MagicMock(amount="2800.00", currency="USD")

        mock_response = MagicMock()
        mock_response.positions = [mock_position1, mock_position2]

        client.stub.GetPositions = AsyncMock(return_value=mock_response)

        portfolio = await client.get_positions("test-user")

        assert portfolio.user_id == "test-user"
        assert portfolio.total_value == 11550.0
        assert len(portfolio.positions) == 2
        assert portfolio.positions[0].symbol == "AAPL"
        assert portfolio.positions[0].quantity == 50
        assert portfolio.positions[0].market_value == 8750.0
        assert portfolio.positions[0].sector == "Unknown"
        assert portfolio.positions[1].symbol == "GOOGL"
        assert portfolio.positions[1].quantity == 20
        assert portfolio.positions[1].market_value == 2800.0

    @pytest.mark.asyncio
    async def test_get_positions_empty(self):
        """Test getting portfolio with no positions."""
        client = PortfolioClient(host="test-host", port=50060)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        mock_response = MagicMock()
        mock_response.positions = []

        client.stub.GetPositions = AsyncMock(return_value=mock_response)

        portfolio = await client.get_positions("test-user")

        assert portfolio.user_id == "test-user"
        assert portfolio.total_value == 0.0
        assert len(portfolio.positions) == 0

    @pytest.mark.asyncio
    async def test_get_positions_auto_connect(self):
        """Test get_positions auto-connects if not connected."""
        client = PortfolioClient(host="test-host", port=50060)

        # Mock the connection
        with patch("src.clients.portfolio_client.grpc.aio.insecure_channel") as mock_channel:
            mock_channel_instance = MagicMock()
            mock_channel.return_value = mock_channel_instance

            with patch(
                "src.clients.portfolio_client.portfolio_pb2_grpc.PortfolioServiceStub"
            ) as mock_stub_class:
                mock_stub = AsyncMock()
                mock_stub_class.return_value = mock_stub

                mock_response = MagicMock()
                mock_response.positions = []
                mock_stub.GetPositions = AsyncMock(return_value=mock_response)

                portfolio = await client.get_positions("test-user")

                # Verify connection was established
                mock_channel.assert_called_once()
                mock_stub_class.assert_called_once()
                assert portfolio.user_id == "test-user"

    @pytest.mark.asyncio
    async def test_get_positions_unavailable_error(self):
        """Test getting positions with unavailable service."""
        client = PortfolioClient(host="test-host", port=50060)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        error.details = MagicMock(return_value="Service unavailable")

        client.stub.GetPositions = AsyncMock(side_effect=error)

        with pytest.raises(ConnectionError) as exc_info:
            await client.get_positions("test-user")

        assert "Portfolio Service unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_positions_timeout_error(self):
        """Test getting positions with timeout."""
        client = PortfolioClient(host="test-host", port=50060)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.DEADLINE_EXCEEDED)
        error.details = MagicMock(return_value="Deadline exceeded")

        client.stub.GetPositions = AsyncMock(side_effect=error)

        with pytest.raises(TimeoutError) as exc_info:
            await client.get_positions("test-user")

        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_positions_other_grpc_error(self):
        """Test getting positions with other gRPC error."""
        client = PortfolioClient(host="test-host", port=50060)
        client.channel = MagicMock()
        client.stub = AsyncMock()

        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.INTERNAL)
        error.details = MagicMock(return_value="Internal error")

        client.stub.GetPositions = AsyncMock(side_effect=error)

        with pytest.raises(grpc.RpcError):
            await client.get_positions("test-user")

    def test_money_to_float(self):
        """Test converting Money proto to float."""
        client = PortfolioClient(host="test-host", port=50060)

        # Valid money
        mock_money = MagicMock(amount="150.25", currency="USD")
        assert client._money_to_float(mock_money) == 150.25

        # Empty amount
        mock_money_empty = MagicMock(amount="", currency="USD")
        assert client._money_to_float(mock_money_empty) == 0.0

        # None
        assert client._money_to_float(None) == 0.0

    @pytest.mark.asyncio
    async def test_get_sector_with_market_data(self, mock_market_data_client, mock_redis_client):
        """Test getting sector with Market Data client."""
        client = PortfolioClient(
            host="test-host",
            port=50060,
            market_data_client=mock_market_data_client,
            redis_client=mock_redis_client,
        )

        # Should return sector from MarketDataService
        assert await client._get_sector("AAPL") == "Technology"
        assert await client._get_sector("XOM") == "Energy"
        assert await client._get_sector("UNKNOWN_SYMBOL") == "Unknown"

    @pytest.mark.asyncio
    async def test_get_sector_without_clients(self):
        """Test getting sector without Market Data client returns Unknown."""
        client = PortfolioClient(host="test-host", port=50060)

        # Without MarketDataClient, should return Unknown
        assert await client._get_sector("AAPL") == "Unknown"
        assert await client._get_sector("GOOGL") == "Unknown"

    @pytest.mark.asyncio
    async def test_get_sector_with_cache_hit(self, mock_market_data_client, mock_redis_client):
        """Test getting sector from cache."""
        mock_redis_client.get = AsyncMock(return_value="CachedSector")

        client = PortfolioClient(
            host="test-host",
            port=50060,
            market_data_client=mock_market_data_client,
            redis_client=mock_redis_client,
        )

        # Should return cached sector without calling MarketDataService
        result = await client._get_sector("AAPL")

        assert result == "CachedSector"
        mock_market_data_client.get_stock_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_sector_caches_result(self, mock_market_data_client, mock_redis_client):
        """Test that sector is cached after fetching from MarketDataService."""
        mock_redis_client.get = AsyncMock(return_value=None)

        client = PortfolioClient(
            host="test-host",
            port=50060,
            market_data_client=mock_market_data_client,
            redis_client=mock_redis_client,
        )

        await client._get_sector("AAPL")

        # Verify cache was written with 24-hour TTL
        mock_redis_client.setex.assert_called_once_with("sector:AAPL", 86400, "Technology")

    @pytest.mark.asyncio
    async def test_get_sector_handles_market_data_error(
        self, mock_market_data_client, mock_redis_client
    ):
        """Test graceful fallback when MarketDataService fails."""
        mock_redis_client.get = AsyncMock(return_value=None)
        mock_market_data_client.get_stock_info = AsyncMock(side_effect=Exception("API Error"))

        client = PortfolioClient(
            host="test-host",
            port=50060,
            market_data_client=mock_market_data_client,
            redis_client=mock_redis_client,
        )

        # Should return Unknown on error
        result = await client._get_sector("AAPL")
        assert result == "Unknown"

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing connection."""
        client = PortfolioClient(host="test-host", port=50060)
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
        client = PortfolioClient(host="test-host", port=50060)

        # Should not raise
        await client.close()

        assert client.channel is None
        assert client.stub is None


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
