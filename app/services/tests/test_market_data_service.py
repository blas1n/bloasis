"""Tests for MarketDataService — yfinance data with cache."""

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services.market_data import MarketDataService, _validate_symbol


@pytest.fixture
def market_data_svc(mock_redis, mock_postgres):
    return MarketDataService(redis=mock_redis, postgres=mock_postgres)


class TestValidateSymbol:
    def test_valid_symbols(self):
        for s in ["AAPL", "MSFT", "BRK.B", "^VIX", "SPY"]:
            _validate_symbol(s)  # should not raise

    def test_invalid_symbols(self):
        for s in ["", "aapl", "TOOLONGSYMBOLX", "DROP TABLE", "123", "A B"]:
            with pytest.raises(ValueError):
                _validate_symbol(s)


class TestGetVIX:
    async def test_returns_cached_vix(self, market_data_svc, mock_redis):
        mock_redis.get.return_value = "25.5"
        vix = await market_data_svc.get_vix()
        assert vix == 25.5

    async def test_fetches_from_yfinance(self, market_data_svc, mock_redis):
        mock_redis.get.return_value = None
        df = pd.DataFrame({"Close": [22.0]}, index=[pd.Timestamp("2024-01-01")])

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_ticker_cls.return_value = mock_ticker
            vix = await market_data_svc.get_vix()

        assert vix == 22.0
        mock_redis.setex.assert_called_once()

    async def test_returns_default_on_error(self, market_data_svc, mock_redis):
        mock_redis.get.side_effect = ValueError("Redis down")
        vix = await market_data_svc.get_vix()
        assert vix == 20.0

    async def test_returns_default_on_empty_history(self, market_data_svc, mock_redis):
        mock_redis.get.return_value = None
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_ticker_cls.return_value = mock_ticker
            vix = await market_data_svc.get_vix()
        assert vix == 20.0


class TestGetAverageVolume:
    async def test_computes_average(self, market_data_svc, mock_redis):
        # Mock the cache_aside decorator's redis.get to return cached OHLCV
        bars = [{"volume": 1000}, {"volume": 2000}, {"volume": 3000}]
        with patch.object(market_data_svc, "get_ohlcv", new_callable=AsyncMock, return_value=bars):
            avg = await market_data_svc.get_average_volume("AAPL", days=3)
        assert avg == 2000.0

    async def test_empty_bars(self, market_data_svc):
        with patch.object(market_data_svc, "get_ohlcv", new_callable=AsyncMock, return_value=[]):
            avg = await market_data_svc.get_average_volume("AAPL")
        assert avg == 0.0


class TestGetOHLCV:
    async def test_fetches_and_formats(self, market_data_svc, mock_redis):
        df = pd.DataFrame(
            {
                "Open": [150.0],
                "High": [155.0],
                "Low": [148.0],
                "Close": [152.0],
                "Volume": [1000000],
            },
            index=[pd.Timestamp("2024-01-01")],
        )
        mock_redis.get.return_value = None
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_ticker_cls.return_value = mock_ticker
            bars = await market_data_svc.get_ohlcv("AAPL", "3mo", "1d")

        assert len(bars) == 1
        assert bars[0]["close"] == 152.0
        assert bars[0]["volume"] == 1000000

    async def test_returns_empty_on_no_data(self, market_data_svc, mock_redis):
        mock_redis.get.return_value = None
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_ticker_cls.return_value = mock_ticker
            bars = await market_data_svc.get_ohlcv("INVALID", "3mo", "1d")
        assert bars == []


class TestGetStockInfo:
    async def test_returns_info(self, market_data_svc, mock_redis):
        mock_redis.get.return_value = None
        mock_info = {
            "shortName": "Apple Inc",
            "sector": "Technology",
            "marketCap": 3_000_000_000_000,
            "trailingPE": 28.5,
            "profitMargins": 0.25,
        }
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.info = mock_info
            mock_ticker_cls.return_value = mock_ticker
            info = await market_data_svc.get_stock_info("AAPL")

        assert info["symbol"] == "AAPL"
        assert info["sector"] == "Technology"
        assert info["pe_ratio"] == 28.5
