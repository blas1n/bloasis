"""Unit tests for MarketDataFetcher."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data_fetcher import MarketDataFetcher


class TestMarketDataFetcher:
    """Tests for MarketDataFetcher."""

    @pytest.fixture
    def fetcher(self) -> MarketDataFetcher:
        """Create a MarketDataFetcher instance."""
        return MarketDataFetcher()

    @pytest.fixture
    def mock_ohlcv_data(self) -> pd.DataFrame:
        """Create mock OHLCV data."""
        return pd.DataFrame({
            "Date": pd.date_range("2024-01-01", periods=5, freq="D"),
            "Open": [150.0, 151.0, 152.0, 153.0, 154.0],
            "High": [155.0, 156.0, 157.0, 158.0, 159.0],
            "Low": [149.0, 150.0, 151.0, 152.0, 153.0],
            "Close": [154.0, 155.0, 156.0, 157.0, 158.0],
            "Volume": [1000000, 1100000, 1200000, 1300000, 1400000],
        }).set_index("Date")

    @pytest.fixture
    def mock_stock_info(self) -> dict:
        """Create mock stock info."""
        return {
            "symbol": "AAPL",
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NASDAQ",
            "currency": "USD",
            "marketCap": 2800000000000,
            "trailingPE": 28.5,
            "dividendYield": 0.005,
            "fiftyTwoWeekHigh": 200.0,
            "fiftyTwoWeekLow": 150.0,
        }

    def test_init(self, fetcher: MarketDataFetcher) -> None:
        """Test fetcher initialization."""
        assert fetcher is not None
        assert fetcher.VALID_INTERVALS
        assert fetcher.VALID_PERIODS

    def test_valid_intervals(self, fetcher: MarketDataFetcher) -> None:
        """Test valid intervals are defined."""
        assert "1d" in fetcher.VALID_INTERVALS
        assert "1h" in fetcher.VALID_INTERVALS
        assert "1m" in fetcher.VALID_INTERVALS
        assert "1wk" in fetcher.VALID_INTERVALS

    def test_valid_periods(self, fetcher: MarketDataFetcher) -> None:
        """Test valid periods are defined."""
        assert "1mo" in fetcher.VALID_PERIODS
        assert "1y" in fetcher.VALID_PERIODS
        assert "max" in fetcher.VALID_PERIODS

    @patch("src.data_fetcher.yf.Ticker")
    def test_get_ohlcv_success(
        self,
        mock_ticker_class: MagicMock,
        fetcher: MarketDataFetcher,
        mock_ohlcv_data: pd.DataFrame,
    ) -> None:
        """Test successful OHLCV fetch."""
        # Setup mock
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_ohlcv_data
        mock_ticker_class.return_value = mock_ticker

        # Call method
        result = fetcher.get_ohlcv("AAPL", interval="1d", period="1mo")

        # Verify
        assert result is not None
        assert len(result) == 5
        assert "open" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns
        mock_ticker.history.assert_called_once()

    @patch("src.data_fetcher.yf.Ticker")
    def test_get_ohlcv_with_dates(
        self,
        mock_ticker_class: MagicMock,
        fetcher: MarketDataFetcher,
        mock_ohlcv_data: pd.DataFrame,
    ) -> None:
        """Test OHLCV fetch with start/end dates."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_ohlcv_data
        mock_ticker_class.return_value = mock_ticker

        result = fetcher.get_ohlcv(
            "AAPL",
            interval="1d",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert result is not None
        mock_ticker.history.assert_called_once_with(
            start="2024-01-01",
            end="2024-01-31",
            interval="1d",
        )

    def test_get_ohlcv_invalid_interval(self, fetcher: MarketDataFetcher) -> None:
        """Test OHLCV fetch with invalid interval."""
        with pytest.raises(ValueError, match="Invalid interval"):
            fetcher.get_ohlcv("AAPL", interval="invalid")

    def test_get_ohlcv_invalid_period(self, fetcher: MarketDataFetcher) -> None:
        """Test OHLCV fetch with invalid period."""
        with pytest.raises(ValueError, match="Invalid period"):
            fetcher.get_ohlcv("AAPL", period="invalid")

    @patch("src.data_fetcher.yf.Ticker")
    def test_get_ohlcv_empty_data(
        self,
        mock_ticker_class: MagicMock,
        fetcher: MarketDataFetcher,
    ) -> None:
        """Test OHLCV fetch with no data returned."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_class.return_value = mock_ticker

        with pytest.raises(ValueError, match="No data available"):
            fetcher.get_ohlcv("INVALID")

    @patch("src.data_fetcher.yf.Ticker")
    def test_get_stock_info_success(
        self,
        mock_ticker_class: MagicMock,
        fetcher: MarketDataFetcher,
        mock_stock_info: dict,
    ) -> None:
        """Test successful stock info fetch."""
        mock_ticker = MagicMock()
        mock_ticker.info = mock_stock_info
        mock_ticker_class.return_value = mock_ticker

        result = fetcher.get_stock_info("AAPL")

        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["name"] == "Apple Inc."
        assert result["sector"] == "Technology"
        assert result["market_cap"] == 2800000000000

    @patch("src.data_fetcher.yf.Ticker")
    def test_get_stock_info_invalid_symbol(
        self,
        mock_ticker_class: MagicMock,
        fetcher: MarketDataFetcher,
    ) -> None:
        """Test stock info fetch with invalid symbol."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_class.return_value = mock_ticker

        with pytest.raises(ValueError, match="No info available"):
            fetcher.get_stock_info("INVALID")

    @patch("src.data_fetcher.yf.Ticker")
    def test_get_batch_ohlcv_success(
        self,
        mock_ticker_class: MagicMock,
        fetcher: MarketDataFetcher,
        mock_ohlcv_data: pd.DataFrame,
    ) -> None:
        """Test batch OHLCV fetch."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_ohlcv_data
        mock_ticker_class.return_value = mock_ticker

        results, failed = fetcher.get_batch_ohlcv(
            symbols=["AAPL", "MSFT", "GOOGL"],
            interval="1d",
            period="1mo",
        )

        assert len(results) == 3
        assert len(failed) == 0
        assert "AAPL" in results
        assert "MSFT" in results
        assert "GOOGL" in results

    @patch("src.data_fetcher.yf.Ticker")
    def test_get_batch_ohlcv_partial_failure(
        self,
        mock_ticker_class: MagicMock,
        fetcher: MarketDataFetcher,
        mock_ohlcv_data: pd.DataFrame,
    ) -> None:
        """Test batch OHLCV fetch with some failures."""
        def mock_history(**kwargs):
            if mock_ticker_class.call_args[0][0] == "INVALID":
                return pd.DataFrame()
            return mock_ohlcv_data

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = mock_history

        def create_ticker(symbol):
            ticker = MagicMock()
            if symbol == "INVALID":
                ticker.history.return_value = pd.DataFrame()
            else:
                ticker.history.return_value = mock_ohlcv_data
            return ticker

        mock_ticker_class.side_effect = create_ticker

        results, failed = fetcher.get_batch_ohlcv(
            symbols=["AAPL", "INVALID", "GOOGL"],
            interval="1d",
            period="1mo",
        )

        assert len(results) == 2
        assert len(failed) == 1
        assert "INVALID" in failed
        assert "AAPL" in results
        assert "GOOGL" in results


class TestMarketDataFetcherIntegration:
    """Integration tests for MarketDataFetcher (requires network)."""

    @pytest.fixture
    def fetcher(self) -> MarketDataFetcher:
        """Create a MarketDataFetcher instance."""
        return MarketDataFetcher()

    @pytest.mark.skip(reason="Integration test - requires network")
    def test_real_ohlcv_fetch(self, fetcher: MarketDataFetcher) -> None:
        """Test real OHLCV fetch (requires network)."""
        result = fetcher.get_ohlcv("AAPL", interval="1d", period="5d")
        assert result is not None
        assert len(result) > 0

    @pytest.mark.skip(reason="Integration test - requires network")
    def test_real_stock_info_fetch(self, fetcher: MarketDataFetcher) -> None:
        """Test real stock info fetch (requires network)."""
        result = fetcher.get_stock_info("AAPL")
        assert result is not None
        assert result["symbol"] == "AAPL"
