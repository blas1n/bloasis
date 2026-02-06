"""
Unit tests for Macro Data Fetcher.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.macro_data import (
    FRED_DEFAULTS,
    FRED_SERIES,
    MacroDataFetcher,
    MockMacroDataFetcher,
)


class TestMockMacroDataFetcher:
    """Tests for MockMacroDataFetcher."""

    @pytest.fixture
    def fetcher(self) -> MockMacroDataFetcher:
        """Create a mock fetcher instance."""
        return MockMacroDataFetcher()

    @pytest.mark.asyncio
    async def test_get_vix(self, fetcher: MockMacroDataFetcher) -> None:
        """Test getting mock VIX."""
        vix = await fetcher.get_vix()
        assert vix == 18.5

    @pytest.mark.asyncio
    async def test_set_mock_vix(self, fetcher: MockMacroDataFetcher) -> None:
        """Test setting mock VIX value."""
        fetcher.set_mock_vix(35.0)
        vix = await fetcher.get_vix()
        assert vix == 35.0

    @pytest.mark.asyncio
    async def test_get_yield_curve(self, fetcher: MockMacroDataFetcher) -> None:
        """Test getting mock yield curve spread."""
        spread = await fetcher.get_yield_curve()
        assert spread == 0.75

    @pytest.mark.asyncio
    async def test_set_mock_yield_spread(self, fetcher: MockMacroDataFetcher) -> None:
        """Test setting mock yield spread."""
        fetcher.set_mock_yield_spread(-0.5)
        spread = await fetcher.get_yield_curve()
        assert spread == -0.5

    @pytest.mark.asyncio
    async def test_get_market_data(self, fetcher: MockMacroDataFetcher) -> None:
        """Test getting mock market data."""
        data = await fetcher.get_market_data()

        assert data["sp500_1m_change"] == 2.5
        assert data["sp500_pe"] == 21.5
        assert data["high_low_ratio"] == 1.2

    @pytest.mark.asyncio
    async def test_get_indicators(self, fetcher: MockMacroDataFetcher) -> None:
        """Test getting all mock indicators."""
        indicators = await fetcher.get_indicators()

        assert indicators["vix"] == 18.5
        assert indicators["yield_curve_10y_2y"] == 0.75
        assert indicators["fed_funds_rate"] == 5.25
        assert indicators["unemployment_rate"] == 3.9
        assert indicators["cpi_yoy"] == 3.2
        assert indicators["gdp_growth"] == 2.5
        assert indicators["sp500_pe"] == 21.5
        assert indicators["credit_spread"] == 350

    @pytest.mark.asyncio
    async def test_get_full_market_data(self, fetcher: MockMacroDataFetcher) -> None:
        """Test getting full mock market data."""
        data = await fetcher.get_full_market_data()

        assert data["vix"] == 18.5
        assert data["sp500_1m_change"] == 2.5
        assert "data_timestamp" in data


class TestMacroDataFetcher:
    """Tests for real MacroDataFetcher with mocked yfinance."""

    @pytest.fixture
    def fetcher(self) -> MacroDataFetcher:
        """Create a fetcher instance."""
        return MacroDataFetcher(fred_api_key=None)

    @pytest.mark.asyncio
    async def test_get_vix_success(self, fetcher: MacroDataFetcher) -> None:
        """Test getting VIX with successful API call."""
        mock_ticker = MagicMock()
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, idx: 22.5)
        )
        mock_ticker.history.return_value = mock_hist

        with patch("src.macro_data.yf.Ticker", return_value=mock_ticker):
            vix = await fetcher.get_vix()
            assert vix == 22.5

    @pytest.mark.asyncio
    async def test_get_vix_failure_returns_default(
        self, fetcher: MacroDataFetcher
    ) -> None:
        """Test getting VIX returns default on failure."""
        with patch("src.macro_data.yf.Ticker", side_effect=Exception("API error")):
            vix = await fetcher.get_vix()
            assert vix == 20.0

    @pytest.mark.asyncio
    async def test_get_vix_empty_history(self, fetcher: MacroDataFetcher) -> None:
        """Test getting VIX returns default on empty history."""
        mock_ticker = MagicMock()
        mock_hist = MagicMock()
        mock_hist.empty = True
        mock_ticker.history.return_value = mock_hist

        with patch("src.macro_data.yf.Ticker", return_value=mock_ticker):
            vix = await fetcher.get_vix()
            assert vix == 20.0

    @pytest.mark.asyncio
    async def test_get_yield_curve_success(self, fetcher: MacroDataFetcher) -> None:
        """Test getting yield curve with successful API calls."""
        mock_tnx = MagicMock()
        mock_tnx_hist = MagicMock()
        mock_tnx_hist.empty = False
        mock_tnx_hist.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, idx: 4.5)
        )
        mock_tnx.history.return_value = mock_tnx_hist

        mock_irx = MagicMock()
        mock_irx_hist = MagicMock()
        mock_irx_hist.empty = False
        mock_irx_hist.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, idx: 4.0)
        )
        mock_irx.history.return_value = mock_irx_hist

        def mock_ticker(symbol: str) -> MagicMock:
            if symbol == "^TNX":
                return mock_tnx
            return mock_irx

        with patch("src.macro_data.yf.Ticker", side_effect=mock_ticker):
            spread = await fetcher.get_yield_curve()
            assert spread == 0.5

    @pytest.mark.asyncio
    async def test_get_yield_curve_failure(self, fetcher: MacroDataFetcher) -> None:
        """Test getting yield curve returns default on failure."""
        with patch("src.macro_data.yf.Ticker", side_effect=Exception("API error")):
            spread = await fetcher.get_yield_curve()
            assert spread == 0.5

    @pytest.mark.asyncio
    async def test_get_market_data_success(self, fetcher: MacroDataFetcher) -> None:
        """Test getting market data with successful API call."""
        mock_ticker = MagicMock()
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 21

        # Mock Close prices
        close_series = MagicMock()
        close_series.iloc = MagicMock(
            __getitem__=lambda self, idx: 450.0 if idx == 0 else 475.0
        )
        mock_hist.__getitem__ = lambda self, key: close_series if key == "Close" else None

        mock_ticker.history.return_value = mock_hist
        mock_ticker.info = {"trailingPE": 22.5}

        with patch("src.macro_data.yf.Ticker", return_value=mock_ticker):
            data = await fetcher.get_market_data()

            assert "sp500_1m_change" in data
            assert "sp500_pe" in data
            assert data["sp500_pe"] == 22.5

    @pytest.mark.asyncio
    async def test_get_market_data_failure(self, fetcher: MacroDataFetcher) -> None:
        """Test getting market data returns defaults on failure."""
        with patch("src.macro_data.yf.Ticker", side_effect=Exception("API error")):
            data = await fetcher.get_market_data()

            assert data["sp500_1m_change"] == 0.0
            assert data["sp500_pe"] == 20.0
            assert data["high_low_ratio"] == 1.0

    @pytest.mark.asyncio
    async def test_get_indicators(self, fetcher: MacroDataFetcher) -> None:
        """Test getting all indicators including FRED data."""
        with patch.object(
            fetcher, "get_vix", new_callable=AsyncMock, return_value=25.0
        ):
            with patch.object(
                fetcher, "get_yield_curve", new_callable=AsyncMock, return_value=0.3
            ):
                with patch.object(
                    fetcher,
                    "get_market_data",
                    new_callable=AsyncMock,
                    return_value={"sp500_1m_change": 1.5, "sp500_pe": 21.0},
                ):
                    with patch.object(
                        fetcher,
                        "get_fred_indicators",
                        new_callable=AsyncMock,
                        return_value=FRED_DEFAULTS.copy(),
                    ):
                        indicators = await fetcher.get_indicators()

                        assert indicators["vix"] == 25.0
                        assert indicators["yield_curve_10y_2y"] == 0.3
                        assert indicators["sp500_1m_change"] == 1.5
                        # FRED-based indicators now included
                        assert indicators["fed_funds_rate"] == 5.25
                        assert indicators["unemployment_rate"] == 3.9
                        assert indicators["cpi_yoy"] == 3.2
                        assert indicators["gdp_growth"] == 2.5
                        assert indicators["credit_spread"] == 350

    @pytest.mark.asyncio
    async def test_get_full_market_data(self, fetcher: MacroDataFetcher) -> None:
        """Test getting full market data."""
        with patch.object(
            fetcher, "get_vix", new_callable=AsyncMock, return_value=18.0
        ):
            with patch.object(
                fetcher,
                "get_market_data",
                new_callable=AsyncMock,
                return_value={
                    "sp500_1m_change": 2.0,
                    "sp500_pe": 20.5,
                    "high_low_ratio": 1.1,
                },
            ):
                data = await fetcher.get_full_market_data()

                assert data["vix"] == 18.0
                assert data["sp500_1m_change"] == 2.0
                assert "data_timestamp" in data

    def test_cache_ttl(self, fetcher: MacroDataFetcher) -> None:
        """Test that cache TTL is set correctly."""
        assert fetcher._cache_ttl == 300  # 5 minutes

    def test_fred_api_key_stored(self) -> None:
        """Test that FRED API key is stored."""
        fetcher = MacroDataFetcher(fred_api_key="test-key")
        assert fetcher.fred_api_key == "test-key"


class TestFredIntegration:
    """Tests for FRED API integration."""

    @pytest.fixture
    def fetcher(self) -> MacroDataFetcher:
        """Create a fetcher instance without FRED API key."""
        return MacroDataFetcher(fred_api_key=None)

    @pytest.mark.asyncio
    async def test_fred_indicators_no_api_key(self, fetcher: MacroDataFetcher) -> None:
        """Test that FRED indicators return defaults when no API key is set."""
        indicators = await fetcher.get_fred_indicators()

        assert indicators == FRED_DEFAULTS

    @pytest.mark.asyncio
    async def test_fred_indicators_with_valid_client(self) -> None:
        """Test FRED indicators with a mocked FRED client."""
        # Create mock FRED client
        mock_fred = MagicMock()

        # Create mock series data
        mock_series = MagicMock()
        mock_series.__len__ = lambda self: 20
        mock_series.iloc.__getitem__ = lambda idx: 5.5

        mock_fred.get_series.return_value = mock_series

        fetcher = MacroDataFetcher(fred_api_key=None)
        fetcher._fred_client = mock_fred

        indicators = await fetcher.get_fred_indicators()

        # All indicators should be present
        assert "fed_funds_rate" in indicators
        assert "unemployment_rate" in indicators
        assert "cpi_yoy" in indicators
        assert "gdp_growth" in indicators
        assert "credit_spread" in indicators

    @pytest.mark.asyncio
    async def test_fred_indicators_caching(self) -> None:
        """Test that FRED indicators are cached for 1 hour."""
        mock_fred = MagicMock()
        mock_series = MagicMock()
        mock_series.__len__ = lambda self: 5
        mock_series.iloc.__getitem__ = lambda idx: 4.5
        mock_fred.get_series.return_value = mock_series

        fetcher = MacroDataFetcher(fred_api_key=None)
        fetcher._fred_client = mock_fred

        # First call should fetch from FRED
        await fetcher.get_fred_indicators()
        first_call_count = mock_fred.get_series.call_count

        # Second call should use cache
        await fetcher.get_fred_indicators()
        second_call_count = mock_fred.get_series.call_count

        # Call count should not increase (cache hit)
        assert first_call_count == second_call_count

    @pytest.mark.asyncio
    async def test_fred_indicators_cache_expiry(self) -> None:
        """Test that FRED cache expires after 1 hour."""
        mock_fred = MagicMock()
        mock_series = MagicMock()
        mock_series.__len__ = lambda self: 5
        mock_series.iloc.__getitem__ = lambda idx: 4.5
        mock_fred.get_series.return_value = mock_series

        fetcher = MacroDataFetcher(fred_api_key=None)
        fetcher._fred_client = mock_fred

        # First call
        await fetcher.get_fred_indicators()
        first_call_count = mock_fred.get_series.call_count

        # Simulate cache expiry by setting old cache time
        fetcher._fred_cache_time = datetime.now() - timedelta(hours=2)

        # Call again - should refetch
        await fetcher.get_fred_indicators()
        second_call_count = mock_fred.get_series.call_count

        # Call count should increase (cache miss)
        assert second_call_count > first_call_count

    @pytest.mark.asyncio
    async def test_fred_indicators_api_error_fallback(self) -> None:
        """Test that API errors fall back to defaults."""
        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = Exception("API Error")

        fetcher = MacroDataFetcher(fred_api_key=None)
        fetcher._fred_client = mock_fred

        indicators = await fetcher.get_fred_indicators()

        # Should return defaults on error
        assert indicators == FRED_DEFAULTS

    @pytest.mark.asyncio
    async def test_fred_indicators_empty_series_fallback(self) -> None:
        """Test that empty series fall back to defaults."""
        mock_fred = MagicMock()
        mock_series = MagicMock()
        mock_series.__len__ = lambda self: 0
        mock_fred.get_series.return_value = mock_series

        fetcher = MacroDataFetcher(fred_api_key=None)
        fetcher._fred_client = mock_fred

        indicators = await fetcher.get_fred_indicators()

        # Should return defaults for empty series
        assert indicators == FRED_DEFAULTS

    @pytest.mark.asyncio
    async def test_fred_indicators_partial_failure(self) -> None:
        """Test that partial API failures still return available data."""
        mock_fred = MagicMock()

        def mock_get_series(series_id: str) -> MagicMock:
            if series_id == "FEDFUNDS":
                mock_series = MagicMock()
                mock_series.__len__ = MagicMock(return_value=5)
                mock_series.iloc = MagicMock()
                mock_series.iloc.__getitem__ = MagicMock(return_value=5.5)
                return mock_series
            raise Exception(f"API Error for {series_id}")

        mock_fred.get_series.side_effect = mock_get_series

        fetcher = MacroDataFetcher(fred_api_key=None)
        fetcher._fred_client = mock_fred

        indicators = await fetcher.get_fred_indicators()

        # fed_funds_rate should have real value
        assert indicators["fed_funds_rate"] == 5.5
        # Others should fall back to defaults
        assert indicators["unemployment_rate"] == FRED_DEFAULTS["unemployment_rate"]

    def test_fred_series_constants(self) -> None:
        """Test that FRED series constants are correctly defined."""
        assert FRED_SERIES["fed_funds_rate"] == "FEDFUNDS"
        assert FRED_SERIES["unemployment_rate"] == "UNRATE"
        assert FRED_SERIES["cpi_yoy"] == "CPIAUCSL"
        assert FRED_SERIES["gdp_growth"] == "GDP"
        assert FRED_SERIES["credit_spread"] == "BAMLH0A0HYM2"

    def test_fred_defaults_values(self) -> None:
        """Test that FRED default values are reasonable."""
        assert FRED_DEFAULTS["fed_funds_rate"] == 5.25
        assert FRED_DEFAULTS["unemployment_rate"] == 3.9
        assert FRED_DEFAULTS["cpi_yoy"] == 3.2
        assert FRED_DEFAULTS["gdp_growth"] == 2.5
        assert FRED_DEFAULTS["credit_spread"] == 350

    def test_fred_cache_ttl(self) -> None:
        """Test that FRED cache TTL is 1 hour (3600 seconds)."""
        fetcher = MacroDataFetcher(fred_api_key=None)
        assert fetcher._fred_cache_ttl == 3600


class TestMockMacroDataFetcherFred:
    """Tests for MockMacroDataFetcher FRED methods."""

    @pytest.fixture
    def fetcher(self) -> MockMacroDataFetcher:
        """Create a mock fetcher instance."""
        return MockMacroDataFetcher()

    @pytest.mark.asyncio
    async def test_get_fred_indicators(self, fetcher: MockMacroDataFetcher) -> None:
        """Test getting mock FRED indicators."""
        indicators = await fetcher.get_fred_indicators()

        assert indicators["fed_funds_rate"] == 5.25
        assert indicators["unemployment_rate"] == 3.9
        assert indicators["cpi_yoy"] == 3.2
        assert indicators["gdp_growth"] == 2.5
        assert indicators["credit_spread"] == 350
