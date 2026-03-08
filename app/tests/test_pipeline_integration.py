"""Integration test — full strategy pipeline (regime → classification → scoring → signals).

Uses real service objects with mocked external I/O boundaries:
Redis, PostgreSQL, LLM client, yfinance.
Core pure functions (factor_scoring, signal_generator, technical_indicators) run for real.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.models import AnalysisResult, RiskProfile
from app.services.classification import ClassificationService
from app.services.market_data import MarketDataService
from app.services.market_regime import MarketRegimeService
from app.services.strategy import StrategyService


def _make_ohlcv_bars(n: int = 60) -> list[dict]:
    """Generate synthetic OHLCV data for testing."""
    bars = []
    base_price = 150.0
    for i in range(n):
        p = base_price + (i * 0.5)
        bars.append(
            {
                "open": p,
                "high": p + 2.0,
                "low": p - 1.0,
                "close": p + 0.5,
                "volume": 1000000 + i * 10000,
            }
        )
    return bars


def _make_stock_info() -> dict:
    return {
        "pe_ratio": 25.0,
        "profit_margin": 0.20,
        "current_ratio": 1.5,
        "return_on_equity": 0.30,
        "debt_to_equity": 0.5,
        "market_cap": 2_000_000_000_000,
    }


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def mock_llm():
    llm = AsyncMock()

    async def analyze_side_effect(
        prompt, system_prompt="", response_format="json", max_tokens=1024
    ):
        if "regime" in system_prompt.lower() or "market regime" in prompt.lower():
            return {
                "regime": "bull",
                "confidence": 0.85,
                "reasoning": "Market is in bullish trend",
            }
        if "sector" in system_prompt.lower() or "candidate" in prompt.lower():
            return {
                "candidates": [
                    {"symbol": "AAPL", "sector": "Technology", "theme": "AI", "score": 85},
                    {"symbol": "MSFT", "sector": "Technology", "theme": "Cloud", "score": 80},
                    {"symbol": "JNJ", "sector": "Healthcare", "theme": "Pharma", "score": 70},
                ]
            }
        # Unified analysis response
        return [
            {
                "symbol": "AAPL",
                "direction": "long",
                "strength": 0.8,
                "entry_price": 180.0,
                "rationale": "Strong momentum in AI sector",
            },
            {
                "symbol": "MSFT",
                "direction": "long",
                "strength": 0.7,
                "entry_price": 420.0,
                "rationale": "Cloud growth",
            },
        ]

    llm.analyze = AsyncMock(side_effect=analyze_side_effect)
    return llm


@pytest.fixture
def mock_market_data_svc(mock_redis):
    svc = AsyncMock(spec=MarketDataService)
    svc.get_ohlcv = AsyncMock(return_value=_make_ohlcv_bars())
    svc.get_stock_info = AsyncMock(return_value=_make_stock_info())
    svc.get_vix = AsyncMock(return_value=18.0)
    return svc


@pytest.fixture
def strategy_svc(mock_redis, mock_llm, mock_market_data_svc):
    mock_postgres = AsyncMock()

    regime_svc = MarketRegimeService(redis=mock_redis, postgres=mock_postgres, llm=mock_llm)
    classification_svc = ClassificationService(redis=mock_redis, llm=mock_llm)

    return StrategyService(
        redis=mock_redis,
        llm=mock_llm,
        market_data=mock_market_data_svc,
        market_regime=regime_svc,
        classification=classification_svc,
    )


class TestFullPipeline:
    @patch("app.services.market_regime.MarketRegimeService._fetch_market_data")
    @patch("app.services.market_regime.MarketRegimeService._fetch_macro_indicators")
    async def test_regime_to_signals(self, mock_macro, mock_market_data, strategy_svc):
        mock_market_data.return_value = {"vix": 18.0, "sp500_1m_change": 2.5, "sp500_trend": "up"}
        mock_macro.return_value = {
            "fed_funds_rate": 5.25,
            "unemployment_rate": 3.8,
            "cpi_yoy": 3.2,
            "credit_spread": 150.0,
            "yield_curve_10y_2y": 0.5,
        }

        result = await strategy_svc.run_analysis(
            user_id="test-user",
            risk_profile=RiskProfile.MODERATE,
        )

        assert isinstance(result, AnalysisResult)
        assert result.regime is not None
        assert result.regime.regime == "bull"
        assert len(result.selected_sectors) > 0
        assert len(result.stock_picks) > 0
        assert len(result.signals) > 0

        for signal in result.signals:
            assert signal.symbol in ("AAPL", "MSFT")
            assert signal.entry_price > 0
            assert signal.stop_loss > 0
            assert signal.take_profit > 0

    @patch("app.services.market_regime.MarketRegimeService._fetch_market_data")
    @patch("app.services.market_regime.MarketRegimeService._fetch_macro_indicators")
    async def test_excluded_sectors_filtered(self, mock_macro, mock_market_data, strategy_svc):
        mock_market_data.return_value = {"vix": 18.0, "sp500_1m_change": 2.5, "sp500_trend": "up"}
        mock_macro.return_value = {
            "fed_funds_rate": 5.25,
            "unemployment_rate": 3.8,
            "cpi_yoy": 3.2,
            "credit_spread": 150.0,
            "yield_curve_10y_2y": 0.5,
        }

        result = await strategy_svc.run_analysis(
            user_id="test-user",
            risk_profile=RiskProfile.MODERATE,
            excluded_sectors=["Technology"],
        )

        assert isinstance(result, AnalysisResult)
        # With Technology excluded, only Healthcare candidates remain
        for pick in result.stock_picks:
            assert pick.sector != "Technology"

    @patch("app.services.market_regime.MarketRegimeService._fetch_market_data")
    @patch("app.services.market_regime.MarketRegimeService._fetch_macro_indicators")
    async def test_pipeline_fallback_on_llm_failure(
        self, mock_macro, mock_market_data, strategy_svc, mock_llm
    ):
        mock_market_data.return_value = {
            "vix": 20.0,
            "sp500_1m_change": 0.0,
            "sp500_trend": "neutral",
        }
        mock_macro.return_value = {
            "fed_funds_rate": 5.25,
            "unemployment_rate": 3.8,
            "cpi_yoy": 3.2,
            "credit_spread": 150.0,
            "yield_curve_10y_2y": 0.5,
        }

        # Make regime LLM call fail
        call_count = 0
        original_side_effect = mock_llm.analyze.side_effect

        async def failing_regime_then_normal(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM service unavailable")
            return await original_side_effect(*args, **kwargs)

        mock_llm.analyze = AsyncMock(side_effect=failing_regime_then_normal)

        result = await strategy_svc.run_analysis(
            user_id="test-user",
            risk_profile=RiskProfile.CONSERVATIVE,
        )

        assert isinstance(result, AnalysisResult)
        # Fallback regime should be "sideways"
        assert result.regime.regime == "sideways"
        assert result.regime.trigger == "fallback"
