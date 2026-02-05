"""Tests for Backtesting Service gRPC clients."""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from src.clients.market_data_client import MarketDataClient


class TestMarketDataClientInit:
    """Tests for MarketDataClient initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default config values."""
        with patch("src.clients.market_data_client.config") as mock_config:
            mock_config.market_data_host = "localhost"
            mock_config.market_data_port = 50052

            client = MarketDataClient()

            assert client.host == "localhost"
            assert client.port == 50052
            assert client.address == "localhost:50052"
            assert client.channel is None
            assert client.stub is None

    def test_init_with_custom_values(self):
        """Test initialization with custom host and port."""
        client = MarketDataClient(host="custom-host", port=9999)

        assert client.host == "custom-host"
        assert client.port == 9999
        assert client.address == "custom-host:9999"


class TestMarketDataClientConnect:
    """Tests for MarketDataClient.connect()."""

    @pytest.mark.asyncio
    async def test_connect_creates_channel_and_stub(self):
        """Test that connect creates channel and stub."""
        client = MarketDataClient(host="test-host", port=50052)

        with patch("src.clients.market_data_client.grpc.aio.insecure_channel") as mock_channel:
            mock_channel_instance = MagicMock()
            mock_channel.return_value = mock_channel_instance

            with patch(
                "src.clients.market_data_client.market_data_pb2_grpc.MarketDataServiceStub"
            ) as mock_stub_class:
                mock_stub = MagicMock()
                mock_stub_class.return_value = mock_stub

                await client.connect()

                mock_channel.assert_called_once_with(
                    "test-host:50052",
                    options=[
                        ("grpc.max_send_message_length", 50 * 1024 * 1024),
                        ("grpc.max_receive_message_length", 50 * 1024 * 1024),
                        ("grpc.keepalive_time_ms", 10000),
                        ("grpc.keepalive_timeout_ms", 5000),
                    ],
                )
                mock_stub_class.assert_called_once_with(mock_channel_instance)
                assert client.channel == mock_channel_instance
                assert client.stub == mock_stub

    @pytest.mark.asyncio
    async def test_connect_already_connected_logs_warning(self):
        """Test that connecting when already connected logs warning."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()  # Simulate already connected

        with patch("src.clients.market_data_client.logger") as mock_logger:
            await client.connect()
            mock_logger.warning.assert_called_once_with("Market Data client already connected")


class TestMarketDataClientGetOhlcv:
    """Tests for MarketDataClient.get_ohlcv()."""

    @pytest.fixture
    def connected_client(self):
        """Create a connected client with mocked stub."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_ohlcv_success(self, connected_client):
        """Test successful OHLCV retrieval."""
        # Create mock bars
        mock_bar1 = MagicMock()
        mock_bar1.timestamp = 1704067200
        mock_bar1.open = 150.0
        mock_bar1.high = 155.0
        mock_bar1.low = 149.0
        mock_bar1.close = 154.0
        mock_bar1.volume = 1000000
        mock_bar1.HasField.return_value = True
        mock_bar1.adj_close = 153.5

        mock_bar2 = MagicMock()
        mock_bar2.timestamp = 1704153600
        mock_bar2.open = 154.0
        mock_bar2.high = 158.0
        mock_bar2.low = 153.0
        mock_bar2.close = 157.0
        mock_bar2.volume = 1200000
        mock_bar2.HasField.return_value = False

        mock_response = MagicMock()
        mock_response.bars = [mock_bar1, mock_bar2]

        connected_client.stub.GetOHLCV = AsyncMock(return_value=mock_response)

        result = await connected_client.get_ohlcv("AAPL", period="1mo", interval="1d")

        assert len(result) == 2
        assert result[0]["timestamp"] == 1704067200
        assert result[0]["open"] == 150.0
        assert result[0]["close"] == 154.0
        assert result[0]["adj_close"] == 153.5
        assert result[1]["adj_close"] is None  # HasField returned False

    @pytest.mark.asyncio
    async def test_get_ohlcv_auto_connects(self):
        """Test that get_ohlcv auto-connects if not connected."""
        client = MarketDataClient(host="test-host", port=50052)

        with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect:
            # After connect, stub should be set
            async def set_stub():
                client.stub = AsyncMock()
                mock_response = MagicMock()
                mock_response.bars = []
                client.stub.GetOHLCV = AsyncMock(return_value=mock_response)

            mock_connect.side_effect = set_stub

            result = await client.get_ohlcv("AAPL")

            mock_connect.assert_called_once()
            assert result == []

    @pytest.mark.asyncio
    async def test_get_ohlcv_unavailable_error(self, connected_client):
        """Test handling of UNAVAILABLE gRPC error."""
        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        error.details = MagicMock(return_value="Service unavailable")

        connected_client.stub.GetOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(ConnectionError) as exc_info:
            await connected_client.get_ohlcv("AAPL")

        assert "Market Data Service unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_ohlcv_timeout_error(self, connected_client):
        """Test handling of DEADLINE_EXCEEDED gRPC error."""
        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.DEADLINE_EXCEEDED)
        error.details = MagicMock(return_value="Deadline exceeded")

        connected_client.stub.GetOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(TimeoutError) as exc_info:
            await connected_client.get_ohlcv("AAPL")

        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_ohlcv_other_grpc_error(self, connected_client):
        """Test handling of other gRPC errors."""
        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.INTERNAL)
        error.details = MagicMock(return_value="Internal error")

        connected_client.stub.GetOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(grpc.RpcError):
            await connected_client.get_ohlcv("AAPL")


class TestMarketDataClientGetBatchOhlcv:
    """Tests for MarketDataClient.get_batch_ohlcv()."""

    @pytest.fixture
    def connected_client(self):
        """Create a connected client with mocked stub."""
        client = MarketDataClient(host="test-host", port=50052)
        client.channel = MagicMock()
        client.stub = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_success(self, connected_client):
        """Test successful batch OHLCV retrieval."""
        # Create mock bars for AAPL
        mock_bar_aapl = MagicMock()
        mock_bar_aapl.timestamp = 1704067200
        mock_bar_aapl.open = 150.0
        mock_bar_aapl.high = 155.0
        mock_bar_aapl.low = 149.0
        mock_bar_aapl.close = 154.0
        mock_bar_aapl.volume = 1000000
        mock_bar_aapl.HasField.return_value = True
        mock_bar_aapl.adj_close = 153.5

        # Create mock bars for GOOGL
        mock_bar_googl = MagicMock()
        mock_bar_googl.timestamp = 1704067200
        mock_bar_googl.open = 140.0
        mock_bar_googl.high = 145.0
        mock_bar_googl.low = 139.0
        mock_bar_googl.close = 144.0
        mock_bar_googl.volume = 800000
        mock_bar_googl.HasField.return_value = False

        mock_aapl_response = MagicMock()
        mock_aapl_response.bars = [mock_bar_aapl]

        mock_googl_response = MagicMock()
        mock_googl_response.bars = [mock_bar_googl]

        mock_response = MagicMock()
        mock_response.data = {"AAPL": mock_aapl_response, "GOOGL": mock_googl_response}

        connected_client.stub.GetBatchOHLCV = AsyncMock(return_value=mock_response)

        result = await connected_client.get_batch_ohlcv(
            ["AAPL", "GOOGL"], period="1mo", interval="1d"
        )

        assert len(result) == 2
        assert "AAPL" in result
        assert "GOOGL" in result
        assert result["AAPL"][0]["close"] == 154.0
        assert result["AAPL"][0]["adj_close"] == 153.5
        assert result["GOOGL"][0]["close"] == 144.0
        assert result["GOOGL"][0]["adj_close"] is None

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_auto_connects(self):
        """Test that get_batch_ohlcv auto-connects if not connected."""
        client = MarketDataClient(host="test-host", port=50052)

        with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect:
            # After connect, stub should be set
            async def set_stub():
                client.stub = AsyncMock()
                mock_response = MagicMock()
                mock_response.data = {}
                client.stub.GetBatchOHLCV = AsyncMock(return_value=mock_response)

            mock_connect.side_effect = set_stub

            result = await client.get_batch_ohlcv(["AAPL"])

            mock_connect.assert_called_once()
            assert result == {}

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_unavailable_error(self, connected_client):
        """Test handling of UNAVAILABLE gRPC error."""
        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        error.details = MagicMock(return_value="Service unavailable")

        connected_client.stub.GetBatchOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(ConnectionError) as exc_info:
            await connected_client.get_batch_ohlcv(["AAPL", "GOOGL"])

        assert "Market Data Service unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_timeout_error(self, connected_client):
        """Test handling of DEADLINE_EXCEEDED gRPC error."""
        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.DEADLINE_EXCEEDED)
        error.details = MagicMock(return_value="Deadline exceeded")

        connected_client.stub.GetBatchOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(TimeoutError) as exc_info:
            await connected_client.get_batch_ohlcv(["AAPL", "GOOGL"])

        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_batch_ohlcv_other_grpc_error(self, connected_client):
        """Test handling of other gRPC errors."""
        error = grpc.RpcError()
        error.code = MagicMock(return_value=grpc.StatusCode.INTERNAL)
        error.details = MagicMock(return_value="Internal error")

        connected_client.stub.GetBatchOHLCV = AsyncMock(side_effect=error)

        with pytest.raises(grpc.RpcError):
            await connected_client.get_batch_ohlcv(["AAPL", "GOOGL"])


class TestMarketDataClientClose:
    """Tests for MarketDataClient.close()."""

    @pytest.mark.asyncio
    async def test_close_when_connected(self):
        """Test closing an active connection."""
        client = MarketDataClient(host="test-host", port=50052)
        mock_channel = AsyncMock()
        client.channel = mock_channel
        client.stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client.channel is None
        assert client.stub is None

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self):
        """Test closing when not connected does nothing."""
        client = MarketDataClient(host="test-host", port=50052)

        # Should not raise any errors
        await client.close()

        assert client.channel is None
        assert client.stub is None
