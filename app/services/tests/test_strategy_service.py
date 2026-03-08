"""Tests for StrategyService — analysis pipeline."""

from unittest.mock import AsyncMock

import pytest

from app.core.models import CandidateSymbol, MarketRegime, MarketRegimeIndicators, RiskProfile
from app.services.strategy import StrategyService


@pytest.fixture
def mock_market_data():
    svc = AsyncMock()
    svc.get_ohlcv = AsyncMock(
        return_value=[
            {
                "timestamp": "2024-01-01",
                "open": 150,
                "high": 155,
                "low": 148,
                "close": 152,
                "volume": 1000000,
            }
            for _ in range(30)
        ]
    )
    svc.get_stock_info = AsyncMock(
        return_value={
            "symbol": "AAPL",
            "sector": "Technology",
            "pe_ratio": 25.0,
            "profit_margin": 0.25,
            "current_ratio": 1.5,
            "return_on_equity": 0.30,
            "debt_to_equity": 0.5,
            "market_cap": 3_000_000_000_000,
        }
    )
    return svc


def _regime():
    return MarketRegime(
        regime="bull",
        confidence=0.85,
        timestamp="2024-01-01T00:00:00",
        trigger="test",
        reasoning="Test regime",
        risk_level="low",
        indicators=MarketRegimeIndicators(vix=15.0),
    )


@pytest.fixture
def mock_market_regime():
    svc = AsyncMock()
    svc.get_current = AsyncMock(return_value=_regime())
    return svc


@pytest.fixture
def mock_classification():
    svc = AsyncMock()
    svc.get_candidates = AsyncMock(
        return_value=[
            CandidateSymbol(symbol="AAPL", sector="Technology", theme="AI", preliminary_score=80.0),
            CandidateSymbol(
                symbol="MSFT", sector="Technology", theme="Cloud", preliminary_score=75.0
            ),
        ]
    )
    return svc


@pytest.fixture
def strategy_svc(mock_redis, mock_llm, mock_market_data, mock_market_regime, mock_classification):
    return StrategyService(
        redis=mock_redis,
        llm=mock_llm,
        market_data=mock_market_data,
        market_regime=mock_market_regime,
        classification=mock_classification,
    )


class TestRunAnalysis:
    async def test_returns_cached_result(self, strategy_svc, mock_redis):
        mock_redis.get.return_value = {
            "user_id": "user-1",
            "regime": {
                "regime": "bull",
                "confidence": 0.85,
                "timestamp": "2024-01-01",
                "trigger": "test",
                "reasoning": "test",
                "risk_level": "low",
            },
            "selected_sectors": ["Technology"],
            "top_themes": [],
            "stock_picks": [],
            "signals": [],
            "cached_at": "2024-01-01",
        }
        result = await strategy_svc.run_analysis("user-1")
        assert result.user_id == "user-1"
        assert result.regime.regime == "bull"

    async def test_corrupted_cache_deleted(self, strategy_svc, mock_redis):
        mock_redis.get.return_value = {"invalid": True}
        result = await strategy_svc.run_analysis("user-1")
        # Should still return a valid result from pipeline
        assert result.user_id == "user-1"
        # Cache was deleted then set again
        mock_redis.delete.assert_called()

    async def test_full_pipeline(self, strategy_svc, mock_redis, mock_llm):
        mock_redis.get.return_value = None
        mock_llm.analyze.return_value = [
            {
                "symbol": "AAPL",
                "direction": "long",
                "strength": 0.8,
                "entry_price": 152,
                "rationale": "Bullish",
            },
        ]

        result = await strategy_svc.run_analysis("user-1", risk_profile=RiskProfile.AGGRESSIVE)
        assert result.user_id == "user-1"
        assert len(result.stock_picks) > 0
        assert len(result.signals) > 0
        mock_redis.setex.assert_called_once()

    async def test_excluded_sectors_filtered(self, strategy_svc, mock_redis, mock_classification):
        mock_redis.get.return_value = None
        result = await strategy_svc.run_analysis("user-1", excluded_sectors=["Technology"])
        # All candidates were Technology, so after filtering → empty
        assert result.stock_picks == []


class TestScoreCandidates:
    async def test_scores_and_ranks(self, strategy_svc, mock_market_data):
        candidates = [
            CandidateSymbol(symbol="AAPL", sector="Technology", theme="AI", preliminary_score=80.0),
            CandidateSymbol(
                symbol="MSFT", sector="Technology", theme="Cloud", preliminary_score=75.0
            ),
        ]
        picks = await strategy_svc._score_candidates(candidates, "bull", "moderate")
        assert len(picks) == 2
        assert picks[0].rank == 1
        assert picks[1].rank == 2
        assert picks[0].final_score >= picks[1].final_score

    async def test_handles_scoring_errors(self, strategy_svc, mock_market_data):
        mock_market_data.get_ohlcv.side_effect = Exception("API error")
        candidates = [
            CandidateSymbol(symbol="AAPL", sector="Technology", theme="AI", preliminary_score=80.0),
        ]
        picks = await strategy_svc._score_candidates(candidates, "bull", "moderate")
        assert picks == []


class TestRunAIAnalysis:
    async def test_returns_list_from_llm(self, strategy_svc, mock_llm):
        mock_llm.analyze.return_value = [{"symbol": "AAPL", "direction": "long"}]
        result = await strategy_svc._run_ai_analysis([], "", _regime(), "moderate", [])
        assert len(result) == 1

    async def test_raises_on_error(self, strategy_svc, mock_llm):
        mock_llm.analyze.side_effect = Exception("LLM error")
        with pytest.raises(RuntimeError, match="AI analysis unavailable"):
            await strategy_svc._run_ai_analysis([], "", _regime(), "moderate", [])

    async def test_returns_empty_on_non_list(self, strategy_svc, mock_llm):
        mock_llm.analyze.return_value = {"not": "a list"}
        result = await strategy_svc._run_ai_analysis([], "", _regime(), "moderate", [])
        assert result == []


class TestGenerateSignals:
    def test_generates_signals(self, strategy_svc):
        analysis = [
            {
                "symbol": "AAPL",
                "direction": "long",
                "strength": 0.8,
                "entry_price": 152,
                "rationale": "Bullish",
            },
        ]
        ohlcv = {
            "AAPL": [
                {
                    "timestamp": "2024-01-01",
                    "open": 150,
                    "high": 155,
                    "low": 148,
                    "close": 152,
                    "volume": 1000000,
                }
                for _ in range(30)
            ]
        }
        signals = strategy_svc._generate_signals(analysis, ohlcv, "low", "moderate")
        assert len(signals) == 1
        assert signals[0].symbol == "AAPL"

    def test_skips_invalid_entries(self, strategy_svc):
        analysis = [
            {"symbol": "", "direction": "long", "strength": 0.8, "entry_price": 100},
            {"symbol": "AAPL", "direction": "long", "strength": 0.8, "entry_price": 0},
        ]
        signals = strategy_svc._generate_signals(analysis, {}, "low", "moderate")
        assert signals == []
