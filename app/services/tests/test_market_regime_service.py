"""Tests for MarketRegimeService — regime classification."""

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services.market_regime import MarketRegimeService


@pytest.fixture
def mock_macro_svc():
    svc = AsyncMock()
    svc.get_indicators = AsyncMock(
        return_value={
            "fed_funds_rate": 5.25,
            "unemployment_rate": 3.8,
            "cpi_yoy": 3.2,
            "credit_spread": 150.0,
        }
    )
    return svc


@pytest.fixture
def regime_svc(mock_redis, mock_postgres, mock_llm, mock_macro_svc):
    return MarketRegimeService(
        redis=mock_redis, postgres=mock_postgres, llm=mock_llm, macro_svc=mock_macro_svc
    )


class TestGetCurrent:
    async def test_returns_from_cache(self, regime_svc, mock_redis):
        mock_redis.get.return_value = {
            "regime": "bull",
            "confidence": 0.85,
            "timestamp": "2024-01-01",
            "trigger": "test",
            "reasoning": "Strong market",
            "risk_level": "low",
        }
        result = await regime_svc.get_current()
        assert result.regime == "bull"
        assert result.confidence == 0.85

    async def test_corrupted_cache_reclassifies(self, regime_svc, mock_redis, mock_llm):
        mock_redis.get.side_effect = [{"invalid": True}, None]
        mock_llm.analyze.return_value = {
            "regime": "sideways",
            "confidence": 0.6,
            "reasoning": "Test",
        }
        with patch.object(regime_svc, "_fetch_market_data", return_value={"vix": 20.0}):
            with patch.object(
                regime_svc, "_fetch_macro_indicators", return_value={"yield_curve_10y_2y": 0.5}
            ):
                result = await regime_svc.get_current()
        assert result.regime == "sideways"
        mock_redis.delete.assert_called()

    async def test_classifies_fresh(self, regime_svc, mock_redis, mock_llm):
        mock_redis.get.return_value = None
        mock_llm.analyze.return_value = {
            "regime": "bear",
            "confidence": 0.75,
            "reasoning": "Downtrend",
        }
        with patch.object(
            regime_svc, "_fetch_market_data", return_value={"vix": 28.0, "sp500_trend": "down"}
        ):
            with patch.object(
                regime_svc,
                "_fetch_macro_indicators",
                return_value={"yield_curve_10y_2y": -0.2},
            ):
                result = await regime_svc.get_current()
        assert result.regime == "bear"
        mock_redis.setex.assert_called_once()


class TestClassify:
    async def test_llm_classification(self, regime_svc, mock_llm):
        mock_llm.analyze.return_value = {
            "regime": "crisis",
            "confidence": 0.95,
            "reasoning": "Market crash",
        }
        with patch.object(regime_svc, "_fetch_market_data", return_value={"vix": 45.0}):
            with patch.object(
                regime_svc, "_fetch_macro_indicators", return_value={"yield_curve_10y_2y": -1.0}
            ):
                result = await regime_svc._classify("manual")
        assert result.regime == "crisis"
        assert result.risk_level == "extreme"

    async def test_fallback_on_llm_error(self, regime_svc, mock_llm):
        mock_llm.analyze.side_effect = RuntimeError("LLM down")
        with patch.object(regime_svc, "_fetch_market_data", return_value={"vix": 20.0}):
            with patch.object(regime_svc, "_fetch_macro_indicators", return_value={}):
                result = await regime_svc._classify("auto")
        assert result.regime == "sideways"
        assert result.trigger == "fallback"


class TestFetchMarketData:
    async def test_fetches_vix_and_sp500(self, regime_svc):
        vix_df = pd.DataFrame({"Close": [25.0]}, index=[pd.Timestamp("2024-01-01")])
        sp_df = pd.DataFrame(
            {"Close": [4500.0, 4600.0]},
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
        )

        with patch("yfinance.Ticker") as mock_ticker_cls:

            def make_ticker(symbol):
                t = MagicMock()
                if symbol == "^VIX":
                    t.history.return_value = vix_df
                else:
                    t.history.return_value = sp_df
                return t

            mock_ticker_cls.side_effect = make_ticker
            data = await regime_svc._fetch_market_data()

        assert data["vix"] == 25.0
        assert data["sp500_trend"] == "up"

    async def test_returns_defaults_on_error(self, regime_svc):
        with patch("yfinance.Ticker", side_effect=ValueError("Network error")):
            data = await regime_svc._fetch_market_data()
        assert data["vix"] == 20.0
        assert data["sp500_trend"] == "neutral"


class TestFetchMacroIndicators:
    async def test_delegates_to_macro_service(self, regime_svc, mock_macro_svc):
        with patch.object(regime_svc, "_fetch_yield_spread", return_value=-0.5):
            data = await regime_svc._fetch_macro_indicators()
        mock_macro_svc.get_indicators.assert_called_once()
        assert data["fed_funds_rate"] == 5.25
        assert data["yield_curve_10y_2y"] == -0.5

    async def test_defaults_without_macro_service(self, mock_redis, mock_postgres, mock_llm):
        svc = MarketRegimeService(redis=mock_redis, postgres=mock_postgres, llm=mock_llm)
        with patch.object(svc, "_fetch_yield_spread", return_value=0.5):
            data = await svc._fetch_macro_indicators()
        assert data["fed_funds_rate"] == 5.25
        assert data["yield_curve_10y_2y"] == 0.5


class TestFetchYieldSpread:
    async def test_fetches_treasury_yields(self, regime_svc):
        tnx_df = pd.DataFrame({"Close": [4.5]}, index=[pd.Timestamp("2024-01-01")])
        irx_df = pd.DataFrame({"Close": [5.0]}, index=[pd.Timestamp("2024-01-01")])

        with patch("yfinance.Ticker") as mock_ticker_cls:

            def make_ticker(symbol):
                t = MagicMock()
                if symbol == "^TNX":
                    t.history.return_value = tnx_df
                elif symbol == "^IRX":
                    t.history.return_value = irx_df
                return t

            mock_ticker_cls.side_effect = make_ticker
            spread = await regime_svc._fetch_yield_spread()

        assert spread == -0.5

    async def test_returns_default_on_error(self, regime_svc):
        with patch("yfinance.Ticker", side_effect=ValueError("Error")):
            spread = await regime_svc._fetch_yield_spread()
        assert spread == 0.5


class TestErrorHandling:
    async def test_fallback_on_fetch_market_data_error(self, regime_svc):
        with patch.object(
            regime_svc, "_fetch_market_data", side_effect=ConnectionError("Network down")
        ):
            with patch.object(regime_svc, "_fetch_macro_indicators", return_value={}):
                result = await regime_svc._classify("auto")
        assert result.regime == "sideways"
        assert result.trigger == "fallback"

    async def test_fallback_on_fetch_macro_error(self, regime_svc):
        with patch.object(regime_svc, "_fetch_market_data", return_value={"vix": 20.0}):
            with patch.object(
                regime_svc, "_fetch_macro_indicators", side_effect=OSError("FRED unavailable")
            ):
                result = await regime_svc._classify("auto")
        assert result.regime == "sideways"
        assert result.trigger == "fallback"

    async def test_fallback_on_llm_auth_error(self, regime_svc, mock_llm):
        mock_llm.analyze.side_effect = Exception("AuthenticationError: Invalid API key")
        with patch.object(regime_svc, "_fetch_market_data", return_value={"vix": 20.0}):
            with patch.object(regime_svc, "_fetch_macro_indicators", return_value={}):
                result = await regime_svc._classify("auto")
        assert result.regime == "sideways"
        assert result.trigger == "fallback"

    async def test_sync_fetch_market_data_catches_broad_exception(self, regime_svc):
        with patch("yfinance.Ticker", side_effect=ConnectionError("Network timeout")):
            data = await regime_svc._fetch_market_data()
        assert data["vix"] == 20.0
        assert data["sp500_trend"] == "neutral"

    async def test_sync_fetch_yield_spread_catches_broad_exception(self, regime_svc):
        with patch("yfinance.Ticker", side_effect=ConnectionError("Network timeout")):
            spread = await regime_svc._fetch_yield_spread()
        assert spread == 0.5

    async def test_get_current_survives_redis_write_failure(self, regime_svc, mock_redis, mock_llm):
        mock_redis.get.return_value = None
        mock_redis.setex.side_effect = ConnectionError("Redis down")
        mock_llm.analyze.return_value = {
            "regime": "bull",
            "confidence": 0.8,
            "reasoning": "Strong market",
        }
        with patch.object(
            regime_svc, "_fetch_market_data", return_value={"vix": 15.0, "sp500_trend": "up"}
        ):
            with patch.object(
                regime_svc, "_fetch_macro_indicators", return_value={"yield_curve_10y_2y": 0.5}
            ):
                result = await regime_svc.get_current()
        assert result.regime == "bull"
        assert result.confidence == 0.8


class TestFallbackRegime:
    def test_returns_conservative_default(self, regime_svc):
        result = regime_svc._fallback_regime()
        assert result.regime == "sideways"
        assert result.confidence == 0.5
        assert result.trigger == "fallback"


class TestFallbackCacheTTL:
    """Fallback regime must use short TTL to allow retry on next cycle."""

    async def test_successful_regime_uses_full_ttl(self, regime_svc, mock_redis, mock_llm):
        """Normal classification → cached with full 6h TTL."""
        mock_redis.get.return_value = None
        mock_llm.analyze.return_value = {
            "regime": "bull",
            "confidence": 0.8,
            "reasoning": "Strong market",
        }
        with patch.object(
            regime_svc, "_fetch_market_data", return_value={"vix": 15.0, "sp500_trend": "up"}
        ):
            with patch.object(
                regime_svc, "_fetch_macro_indicators", return_value={"yield_curve_10y_2y": 0.5}
            ):
                result = await regime_svc.get_current()

        assert result.trigger == "baseline"
        ttl_used = mock_redis.setex.call_args[0][1]
        # Full TTL should be >> 300 seconds (5 min fallback TTL)
        assert ttl_used > 300

    async def test_fallback_regime_uses_short_ttl(self, regime_svc, mock_redis, mock_llm):
        """LLM failure → fallback cached with short 5-min TTL, not 6h."""
        mock_redis.get.return_value = None
        mock_llm.analyze.side_effect = RuntimeError("LLM unavailable")
        with patch.object(regime_svc, "_fetch_market_data", return_value={"vix": 20.0}):
            with patch.object(regime_svc, "_fetch_macro_indicators", return_value={}):
                result = await regime_svc.get_current()

        assert result.trigger == "fallback"
        ttl_used = mock_redis.setex.call_args[0][1]
        # Fallback must use short TTL (300s = 5 min) so the next cycle retries LLM
        assert ttl_used == 300
