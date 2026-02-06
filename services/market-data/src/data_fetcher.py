"""Market data fetcher using yfinance."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

import pandas as pd
import yfinance as yf

if TYPE_CHECKING:
    from .repository import MarketDataRepository

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """Fetches market data from Yahoo Finance using yfinance."""

    # Valid intervals for yfinance
    VALID_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}

    # Valid periods for yfinance
    VALID_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}

    def __init__(self) -> None:
        """Initialize the data fetcher."""
        pass

    def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1d",
        period: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for a symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")
            interval: Data interval ("1m", "5m", "1h", "1d", "1wk", "1mo")
            period: Data period ("1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max")
            start_date: Start date (ISO format) - overrides period
            end_date: End date (ISO format)

        Returns:
            DataFrame with OHLCV data

        Raises:
            ValueError: If symbol is invalid or no data available
        """
        # Validate interval
        if interval not in self.VALID_INTERVALS:
            raise ValueError(f"Invalid interval: {interval}. Valid intervals: {self.VALID_INTERVALS}")

        # Validate period if provided
        if period and period not in self.VALID_PERIODS:
            raise ValueError(f"Invalid period: {period}. Valid periods: {self.VALID_PERIODS}")

        try:
            ticker = yf.Ticker(symbol)

            # Use date range if provided, otherwise use period
            if start_date and end_date:
                hist = ticker.history(
                    start=start_date,
                    end=end_date,
                    interval=interval,
                )
            else:
                hist = ticker.history(
                    period=period or "1mo",
                    interval=interval,
                )

            if hist.empty:
                raise ValueError(f"No data available for symbol: {symbol}")

            # Standardize column names to lowercase
            hist.columns = [col.lower().replace(" ", "_") for col in hist.columns]

            # Reset index to get timestamp as a column
            hist = hist.reset_index()

            # Rename 'Date' or 'Datetime' column to 'timestamp'
            if "date" in hist.columns:
                hist = hist.rename(columns={"date": "timestamp"})
            elif "datetime" in hist.columns:
                hist = hist.rename(columns={"datetime": "timestamp"})

            logger.info(f"Fetched {len(hist)} bars for {symbol}")
            return hist

        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            raise ValueError(f"Failed to fetch data for {symbol}: {e}")

    def get_stock_info(self, symbol: str) -> dict:
        """
        Fetch stock metadata/info.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dictionary with stock info

        Raises:
            ValueError: If symbol is invalid
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or "symbol" not in info:
                raise ValueError(f"No info available for symbol: {symbol}")

            # Extract relevant fields with safe defaults
            result = {
                "symbol": info.get("symbol", symbol),
                "name": info.get("longName") or info.get("shortName", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "exchange": info.get("exchange", ""),
                "currency": info.get("currency", "USD"),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "return_on_equity": info.get("returnOnEquity"),
                # yfinance returns D/E as percentage, convert to ratio
                "debt_to_equity": (
                    info.get("debtToEquity") / 100.0
                    if info.get("debtToEquity") is not None
                    else None
                ),
                "current_ratio": info.get("currentRatio"),
                "profit_margin": info.get("profitMargins"),
            }

            logger.info(f"Fetched info for {symbol}")
            return result

        except Exception as e:
            logger.error(f"Error fetching info for {symbol}: {e}")
            raise ValueError(f"Failed to fetch info for {symbol}: {e}")

    def get_batch_ohlcv(
        self,
        symbols: list[str],
        interval: str = "1d",
        period: str = "1mo",
    ) -> tuple[dict[str, pd.DataFrame], list[str]]:
        """
        Fetch OHLCV data for multiple symbols.

        Args:
            symbols: List of stock ticker symbols
            interval: Data interval
            period: Data period

        Returns:
            Tuple of (data dict mapping symbol to DataFrame, list of failed symbols)
        """
        results: dict[str, pd.DataFrame] = {}
        failed: list[str] = []

        for symbol in symbols:
            try:
                df = self.get_ohlcv(symbol, interval=interval, period=period)
                results[symbol] = df
            except ValueError as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")
                failed.append(symbol)

        logger.info(f"Batch fetch complete: {len(results)} succeeded, {len(failed)} failed")
        return results, failed

    async def fetch_and_store_ohlcv(
        self,
        symbol: str,
        interval: str,
        repository: MarketDataRepository,
        full_refresh: bool = False,
    ) -> int:
        """
        Fetch OHLCV data and store in database.

        Performs incremental fetch by default (only new data).
        Set full_refresh=True to re-fetch all data.

        Args:
            symbol: Stock ticker symbol
            interval: Data interval ("1d", "1h", etc.)
            repository: MarketDataRepository instance
            full_refresh: Whether to re-fetch all data

        Returns:
            Number of new bars stored
        """
        start_date: Optional[str] = None
        end_date: Optional[str] = None
        period: Optional[str] = None

        if not full_refresh:
            # Get latest stored timestamp for incremental sync
            latest_time = await repository.get_latest_ohlcv_time(symbol, interval)
            if latest_time:
                # Fetch from day after latest stored data
                start_dt = latest_time + timedelta(days=1)
                start_date = start_dt.strftime("%Y-%m-%d")
                end_date = datetime.now().strftime("%Y-%m-%d")
                logger.info(
                    f"Incremental sync for {symbol}: from {start_date} to {end_date}"
                )
            else:
                # No existing data, fetch full history
                period = "5y"
                logger.info(f"Initial sync for {symbol}: fetching 5 years of data")
        else:
            # Full refresh - fetch all available data
            period = "max"
            logger.info(f"Full refresh for {symbol}: fetching all available data")

        try:
            df = self.get_ohlcv(
                symbol=symbol,
                interval=interval,
                period=period,
                start_date=start_date,
                end_date=end_date,
            )

            if df.empty:
                logger.info(f"No new data for {symbol}")
                return 0

            # Store in database
            rows_stored = await repository.save_ohlcv(symbol, interval, df)
            logger.info(f"Stored {rows_stored} bars for {symbol}")
            return rows_stored

        except ValueError as e:
            # No data available is not an error for incremental sync
            if "No data available" in str(e) and not full_refresh:
                logger.debug(f"No new data available for {symbol}")
                return 0
            raise

    async def sync_stock_info(
        self,
        symbol: str,
        repository: MarketDataRepository,
    ) -> bool:
        """
        Fetch and store stock info.

        Args:
            symbol: Stock ticker symbol
            repository: MarketDataRepository instance

        Returns:
            True if successful
        """
        try:
            info = self.get_stock_info(symbol)
            await repository.save_stock_info(symbol, info)
            logger.info(f"Synced stock info for {symbol}")
            return True
        except ValueError as e:
            logger.error(f"Failed to sync stock info for {symbol}: {e}")
            return False
