"""Pytest configuration and fixtures for Classification Service tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.clients.market_regime_client import MarketRegimeClient
from src.service import ClassificationService
from src.utils.cache import CacheManager


@pytest.fixture
def mock_cache():
    """Mock cache manager."""
    cache = AsyncMock(spec=CacheManager)
    cache.get = AsyncMock(return_value=None)  # Default: cache miss
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    cache.connect = AsyncMock()
    cache.close = AsyncMock()
    return cache


@pytest.fixture
def mock_regime_client():
    """Mock Market Regime client."""
    client = AsyncMock(spec=MarketRegimeClient)

    mock_response = MagicMock()
    mock_response.regime = "bull"
    mock_response.confidence = 0.85
    mock_response.timestamp = "2026-02-02T12:00:00Z"
    mock_response.trigger = "baseline"

    client.get_current_regime = AsyncMock(return_value=mock_response)
    client.connect = AsyncMock()
    client.close = AsyncMock()

    return client


@pytest.fixture
def mock_analyst():
    """Mock Claude analyst returning valid sector/theme data."""
    analyst = AsyncMock()
    analyst.analyze = AsyncMock(side_effect=_analyst_side_effect)
    return analyst


def _analyst_side_effect(**kwargs) -> dict:
    """Return appropriate mock data based on prompt content."""
    prompt = kwargs.get("prompt", "")
    # Theme prompt contains 'themes' keyword; sector prompt contains 'sector'
    if "theme" in prompt.lower():
        return {
            "themes": [
                {
                    "theme": "AI Infrastructure",
                    "sector": "Technology",
                    "score": 92.0,
                    "rationale": "AI drives tech demand",
                    "representative_symbols": ["NVDA", "AMD", "TSM"],
                },
                {
                    "theme": "Cloud Computing",
                    "sector": "Technology",
                    "score": 88.0,
                    "rationale": "Cloud adoption accelerating",
                    "representative_symbols": ["MSFT", "GOOGL", "AMZN"],
                },
                {
                    "theme": "Biotech Innovation",
                    "sector": "Healthcare",
                    "score": 85.0,
                    "rationale": "Drug pipeline momentum",
                    "representative_symbols": ["MRNA", "REGN", "VRTX"],
                },
            ]
        }
    # Default: sector analysis response
    return {
        "sectors": [
            {"sector": "Technology", "score": 90.0, "rationale": "Growth leader", "selected": True},
            {"sector": "Healthcare", "score": 75.0, "rationale": "Defensive growth", "selected": True},
            {"sector": "Financials", "score": 68.0, "rationale": "Rate sensitive", "selected": False},
            {"sector": "Consumer Discretionary", "score": 65.0, "rationale": "Mixed signals", "selected": False},
            {"sector": "Industrials", "score": 60.0, "rationale": "Neutral", "selected": False},
            {"sector": "Communication Services", "score": 58.0, "rationale": "Neutral", "selected": False},
            {"sector": "Consumer Staples", "score": 55.0, "rationale": "Defensive", "selected": False},
            {"sector": "Energy", "score": 50.0, "rationale": "Volatile", "selected": False},
            {"sector": "Utilities", "score": 45.0, "rationale": "Low growth", "selected": False},
            {"sector": "Real Estate", "score": 42.0, "rationale": "Rate risk", "selected": False},
            {"sector": "Materials", "score": 40.0, "rationale": "Cyclical", "selected": False},
        ]
    }


@pytest.fixture
def classification_service(mock_analyst, mock_regime_client, mock_cache):
    """Create Classification Service with mocked Claude analyst."""
    return ClassificationService(
        analyst=mock_analyst,
        regime_client=mock_regime_client,
        cache_manager=mock_cache,
    )
