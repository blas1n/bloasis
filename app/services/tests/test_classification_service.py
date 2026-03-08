"""Tests for ClassificationService — sector/theme filtering."""

import pytest

from app.services.classification import ClassificationService


@pytest.fixture
def classification_svc(mock_redis, mock_llm):
    return ClassificationService(redis=mock_redis, llm=mock_llm)


class TestGetCandidates:
    async def test_returns_from_cache(self, classification_svc, mock_redis):
        mock_redis.get.return_value = [
            {"symbol": "AAPL", "sector": "Technology", "theme": "AI", "preliminary_score": 80.0},
        ]
        result = await classification_svc.get_candidates("bull")
        assert len(result) == 1
        assert result[0].symbol == "AAPL"

    async def test_classifies_and_caches(self, classification_svc, mock_redis, mock_llm):
        mock_redis.get.return_value = None
        mock_llm.analyze.return_value = {
            "candidates": [
                {"symbol": "AAPL", "sector": "Technology", "theme": "AI", "score": 85.0},
                {"symbol": "MSFT", "sector": "Technology", "theme": "Cloud", "score": 80.0},
            ]
        }
        result = await classification_svc.get_candidates("bull")
        assert len(result) == 2
        assert result[0].symbol == "AAPL"
        mock_redis.setex.assert_called_once()


class TestClassify:
    async def test_parses_llm_response(self, classification_svc, mock_llm):
        mock_llm.analyze.return_value = {
            "candidates": [
                {"symbol": "NVDA", "sector": "Technology", "theme": "AI", "score": 90.0},
            ]
        }
        result = await classification_svc._classify("bull")
        assert len(result) == 1
        assert result[0].symbol == "NVDA"

    async def test_fallback_on_error(self, classification_svc, mock_llm):
        mock_llm.analyze.side_effect = RuntimeError("LLM error")
        result = await classification_svc._classify("crisis")
        assert len(result) == 10  # fallback has 10 defaults
        assert result[0].symbol == "AAPL"

    async def test_fallback_on_empty_response(self, classification_svc, mock_llm):
        mock_llm.analyze.return_value = {"candidates": []}
        result = await classification_svc._classify("bear")
        assert len(result) == 10  # fallback


class TestParseCandidates:
    def test_valid_data(self, classification_svc):
        data = {
            "candidates": [
                {"symbol": "AAPL", "sector": "Tech", "theme": "AI", "score": 85},
            ]
        }
        result = classification_svc._parse_candidates(data, "bull")
        assert len(result) == 1

    def test_invalid_data_returns_fallback(self, classification_svc):
        result = classification_svc._parse_candidates("not a dict", "bull")
        assert len(result) == 10

    def test_caps_at_50(self, classification_svc):
        data = {
            "candidates": [
                {"symbol": f"SYM{i}", "sector": "Tech", "theme": "X", "score": 50}
                for i in range(60)
            ]
        }
        result = classification_svc._parse_candidates(data, "bull")
        assert len(result) == 50


class TestFallbackCandidates:
    def test_returns_default_list(self, classification_svc):
        result = classification_svc._fallback_candidates()
        assert len(result) == 10
        symbols = [c.symbol for c in result]
        assert "AAPL" in symbols
        assert "JPM" in symbols
