"""
Macro Economic Data Fetcher.

Fetches macro economic indicators for market regime classification.
Uses yfinance for market data and supports FRED API for economic indicators.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import yfinance as yf
from fredapi import Fred

logger = logging.getLogger(__name__)

# FRED series IDs for economic indicators
FRED_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "unemployment_rate": "UNRATE",
    "cpi_yoy": "CPIAUCSL",
    "gdp_growth": "GDP",
    "credit_spread": "BAMLH0A0HYM2",
}

# Default fallback values when FRED data is unavailable
FRED_DEFAULTS = {
    "fed_funds_rate": 5.25,
    "unemployment_rate": 3.9,
    "cpi_yoy": 3.2,
    "gdp_growth": 2.5,
    "credit_spread": 350,
}


class MacroDataFetcher:
    """
    Fetches macro economic indicators for market analysis.

    Provides data including VIX, yield curves, and market indices.
    Uses yfinance for real-time data with fallbacks for development.
    """

    def __init__(self, fred_api_key: Optional[str] = None) -> None:
        """
        Initialize the macro data fetcher.

        Args:
            fred_api_key: Optional FRED API key for economic data.
        """
        self.fred_api_key = fred_api_key
        self._cache: dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minutes
        self._fred_cache: dict[str, Any] = {}
        self._fred_cache_ttl = 3600  # 1 hour for FRED data
        self._fred_cache_time: Optional[datetime] = None
        self._fred_client: Optional[Any] = None

        # Initialize FRED client if API key is available
        if self.fred_api_key:
            try:
                self._fred_client = Fred(api_key=self.fred_api_key)
                logger.info("FRED API client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize FRED client: {e}")
                self._fred_client = None

    async def get_indicators(self) -> dict[str, Any]:
        """
        Get current macro economic indicators.

        Returns:
            Dictionary containing:
            - vix: Current VIX level
            - yield_curve_10y_2y: 10Y-2Y Treasury spread
            - fed_funds_rate: Federal funds rate
            - unemployment_rate: Unemployment rate
            - cpi_yoy: Year-over-year CPI inflation
            - gdp_growth: GDP growth rate
            - sp500_pe: S&P 500 P/E ratio
            - credit_spread: High Yield - Investment Grade spread
        """
        indicators = {}

        # Get VIX
        indicators["vix"] = await self.get_vix()

        # Get yield curve
        indicators["yield_curve_10y_2y"] = await self.get_yield_curve()

        # Get market data
        market_data = await self.get_market_data()
        indicators.update(market_data)

        # Get FRED economic indicators
        fred_data = await self.get_fred_indicators()
        indicators.update(fred_data)

        return indicators

    async def get_fred_indicators(self) -> dict[str, Any]:
        """
        Get economic indicators from FRED API.

        Returns cached data if available and not expired.
        Falls back to default values if FRED is unavailable.

        Returns:
            Dictionary containing:
            - fed_funds_rate: Federal funds rate
            - unemployment_rate: Unemployment rate
            - cpi_yoy: Year-over-year CPI inflation
            - gdp_growth: GDP growth rate
            - credit_spread: High Yield - Investment Grade spread
        """
        # Check if cached data is still valid
        if self._fred_cache and self._fred_cache_time:
            cache_age = (datetime.now() - self._fred_cache_time).total_seconds()
            if cache_age < self._fred_cache_ttl:
                logger.debug("Returning cached FRED data")
                return self._fred_cache.copy()

        # If FRED client is not available, return defaults
        if not self._fred_client:
            logger.debug("FRED client unavailable, using default values")
            return FRED_DEFAULTS.copy()

        # Fetch data from FRED
        indicators: dict[str, Any] = {}

        for indicator_name, series_id in FRED_SERIES.items():
            try:
                series = self._fred_client.get_series(series_id)
                if series is not None and len(series) > 0:
                    # Get the most recent value
                    latest_value = float(series.iloc[-1])

                    # Special handling for CPI (calculate YoY change)
                    if indicator_name == "cpi_yoy" and len(series) >= 12:
                        current = float(series.iloc[-1])
                        year_ago = float(series.iloc[-13])
                        if year_ago > 0:
                            latest_value = ((current - year_ago) / year_ago) * 100

                    # Special handling for GDP (calculate growth rate)
                    elif indicator_name == "gdp_growth" and len(series) >= 4:
                        current = float(series.iloc[-1])
                        year_ago = float(series.iloc[-5])
                        if year_ago > 0:
                            latest_value = ((current - year_ago) / year_ago) * 100

                    indicators[indicator_name] = latest_value
                    logger.debug(f"Fetched {indicator_name}: {latest_value}")
                else:
                    indicators[indicator_name] = FRED_DEFAULTS[indicator_name]
                    logger.warning(f"Empty series for {series_id}, using default")
            except Exception as e:
                indicators[indicator_name] = FRED_DEFAULTS[indicator_name]
                logger.warning(f"Failed to fetch {series_id}: {e}, using default")

        # Cache the results
        self._fred_cache = indicators.copy()
        self._fred_cache_time = datetime.now()

        return indicators

    async def get_vix(self) -> float:
        """
        Get current VIX level.

        Returns:
            Current VIX value or default of 20.0 on error.
        """
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as e:
            logger.warning(f"Failed to fetch VIX: {e}")

        return 20.0  # Default VIX

    async def get_yield_curve(self) -> float:
        """
        Get 10Y-2Y Treasury yield spread.

        Returns:
            Yield spread in percentage points.
        """
        try:
            # 10-Year Treasury
            tnx = yf.Ticker("^TNX")
            tnx_hist = tnx.history(period="1d")

            # 2-Year Treasury (using proxy)
            two_year = yf.Ticker("^IRX")  # 13-week T-bill as proxy
            two_year_hist = two_year.history(period="1d")

            if not tnx_hist.empty and not two_year_hist.empty:
                yield_10y = float(tnx_hist["Close"].iloc[-1])
                yield_2y = float(two_year_hist["Close"].iloc[-1])
                return yield_10y - yield_2y
        except Exception as e:
            logger.warning(f"Failed to fetch yield curve: {e}")

        return 0.5  # Default positive spread

    async def get_market_data(self) -> dict[str, Any]:
        """
        Get market index data.

        Returns:
            Dictionary with market data including S&P 500 changes.
        """
        data: dict[str, Any] = {
            "sp500_1m_change": 0.0,
            "sp500_pe": 20.0,
            "high_low_ratio": 1.0,
        }

        try:
            spy = yf.Ticker("SPY")

            # Get 1-month history
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            hist = spy.history(start=start_date, end=end_date)

            if not hist.empty and len(hist) > 1:
                start_price = float(hist["Close"].iloc[0])
                end_price = float(hist["Close"].iloc[-1])
                data["sp500_1m_change"] = ((end_price - start_price) / start_price) * 100

            # Get PE ratio if available
            info = spy.info
            if "trailingPE" in info:
                data["sp500_pe"] = float(info["trailingPE"])

        except Exception as e:
            logger.warning(f"Failed to fetch market data: {e}")

        return data

    async def get_full_market_data(self) -> dict[str, Any]:
        """
        Get comprehensive market data for AI analysis.

        Returns:
            Dictionary with all market indicators needed for classification.
        """
        market_data: dict[str, Any] = {}

        # Get VIX
        market_data["vix"] = await self.get_vix()

        # Get market index data
        index_data = await self.get_market_data()
        market_data.update(index_data)

        # Add additional context
        market_data["data_timestamp"] = datetime.utcnow().isoformat()

        return market_data


class MockMacroDataFetcher(MacroDataFetcher):
    """Mock data fetcher for testing without network calls."""

    def __init__(self, fred_api_key: Optional[str] = None) -> None:
        """Initialize mock fetcher."""
        super().__init__(fred_api_key)
        self._mock_vix = 18.5
        self._mock_yield_spread = 0.75

    def set_mock_vix(self, vix: float) -> None:
        """Set mock VIX value for testing."""
        self._mock_vix = vix

    def set_mock_yield_spread(self, spread: float) -> None:
        """Set mock yield spread for testing."""
        self._mock_yield_spread = spread

    async def get_indicators(self) -> dict[str, Any]:
        """Return mock indicators."""
        return {
            "vix": self._mock_vix,
            "yield_curve_10y_2y": self._mock_yield_spread,
            "fed_funds_rate": 5.25,
            "unemployment_rate": 3.9,
            "cpi_yoy": 3.2,
            "gdp_growth": 2.5,
            "sp500_pe": 21.5,
            "credit_spread": 350,
        }

    async def get_vix(self) -> float:
        """Return mock VIX."""
        return self._mock_vix

    async def get_yield_curve(self) -> float:
        """Return mock yield curve spread."""
        return self._mock_yield_spread

    async def get_market_data(self) -> dict[str, Any]:
        """Return mock market data."""
        return {
            "sp500_1m_change": 2.5,
            "sp500_pe": 21.5,
            "high_low_ratio": 1.2,
        }

    async def get_fred_indicators(self) -> dict[str, Any]:
        """Return mock FRED indicators."""
        return {
            "fed_funds_rate": 5.25,
            "unemployment_rate": 3.9,
            "cpi_yoy": 3.2,
            "gdp_growth": 2.5,
            "credit_spread": 350,
        }

    async def get_full_market_data(self) -> dict[str, Any]:
        """Return mock full market data."""
        return {
            "vix": self._mock_vix,
            "sp500_1m_change": 2.5,
            "sp500_pe": 21.5,
            "high_low_ratio": 1.2,
            "data_timestamp": datetime.utcnow().isoformat(),
        }
