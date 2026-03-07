"""Tests for MacroService — FRED API integration."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.macro import DEFAULTS, MacroService


@pytest.fixture
def macro_svc(mock_redis):
    return MacroService(redis=mock_redis)


class TestGetIndicators:
    async def test_returns_from_cache(self, macro_svc, mock_redis):
        cached = {
            "fed_funds_rate": 5.5,
            "unemployment_rate": 3.7,
            "cpi_yoy": 3.0,
            "credit_spread": 140.0,
        }
        mock_redis.get.return_value = cached
        result = await macro_svc.get_indicators()
        assert result == cached
        mock_redis.setex.assert_not_called()

    async def test_fetches_fresh_and_caches(self, macro_svc, mock_redis):
        with patch.object(macro_svc, "_fetch_from_fred", return_value=dict(DEFAULTS)):
            result = await macro_svc.get_indicators()
        assert result == DEFAULTS
        mock_redis.setex.assert_called_once()


class TestFetchFromFred:
    async def test_returns_defaults_when_no_api_key(self, macro_svc):
        with patch("app.services.macro.settings") as mock_settings:
            mock_settings.fred_api_key = ""
            result = await macro_svc._fetch_from_fred()
        assert result == DEFAULTS

    async def test_returns_defaults_on_exception(self, macro_svc):
        with patch("app.services.macro.settings") as mock_settings:
            mock_settings.fred_api_key = "test-key"
            with patch("asyncio.to_thread", side_effect=Exception("Connection error")):
                result = await macro_svc._fetch_from_fred()
        assert result == DEFAULTS

    async def test_calls_fred_api_when_key_configured(self, macro_svc):
        expected = {
            "fed_funds_rate": 5.0,
            "unemployment_rate": 3.5,
            "cpi_yoy": 2.8,
            "credit_spread": 130.0,
        }
        with patch("app.services.macro.settings") as mock_settings:
            mock_settings.fred_api_key = "test-key"
            with patch("asyncio.to_thread", return_value=expected):
                result = await macro_svc._fetch_from_fred()
        assert result == expected


class TestSyncFetch:
    def test_fetches_all_series(self, macro_svc):
        mock_fred = MagicMock()
        # Fed funds rate
        mock_fred.get_series.side_effect = [
            pd.Series([5.33], index=[pd.Timestamp("2024-01-01")]),  # FEDFUNDS
            pd.Series([3.7], index=[pd.Timestamp("2024-01-01")]),  # UNRATE
            pd.Series(  # CPIAUCSL (14 months for YoY calc)
                [300.0 + i for i in range(14)],
                index=pd.date_range("2023-01-01", periods=14, freq="MS"),
            ),
            pd.Series([4.5], index=[pd.Timestamp("2024-01-01")]),  # BAMLH0A0HYM2
        ]

        with patch("app.services.macro.settings") as mock_settings:
            mock_settings.fred_api_key = "test-key"
            with patch("fredapi.Fred", return_value=mock_fred):
                result = macro_svc._sync_fetch()

        assert result["fed_funds_rate"] == 5.33
        assert result["unemployment_rate"] == 3.7
        assert result["credit_spread"] == 450.0  # 4.5 * 100

    def test_partial_failure_uses_defaults(self, macro_svc):
        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [
            pd.Series([5.33], index=[pd.Timestamp("2024-01-01")]),  # FEDFUNDS ok
            Exception("FRED error"),  # UNRATE fails
            Exception("FRED error"),  # CPIAUCSL fails
            Exception("FRED error"),  # BAMLH0A0HYM2 fails
        ]

        with patch("app.services.macro.settings") as mock_settings:
            mock_settings.fred_api_key = "test-key"
            with patch("fredapi.Fred", return_value=mock_fred):
                result = macro_svc._sync_fetch()

        assert result["fed_funds_rate"] == 5.33  # Fetched
        assert result["unemployment_rate"] == DEFAULTS["unemployment_rate"]  # Default
        assert result["cpi_yoy"] == DEFAULTS["cpi_yoy"]  # Default

    def test_cpi_yoy_calculation(self, macro_svc):
        mock_fred = MagicMock()
        # CPI: current=310, year_ago=300 → YoY = (310-300)/300*100 = 3.3%
        cpi_series = pd.Series(
            [300.0] * 12 + [310.0],
            index=pd.date_range("2023-01-01", periods=13, freq="MS"),
        )
        mock_fred.get_series.side_effect = [
            pd.Series([5.0]),  # FEDFUNDS
            pd.Series([3.8]),  # UNRATE
            cpi_series,  # CPIAUCSL
            pd.Series([1.5]),  # BAMLH0A0HYM2
        ]

        with patch("app.services.macro.settings") as mock_settings:
            mock_settings.fred_api_key = "test-key"
            with patch("fredapi.Fred", return_value=mock_fred):
                result = macro_svc._sync_fetch()

        assert result["cpi_yoy"] == 3.3
