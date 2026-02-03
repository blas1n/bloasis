"""Pytest fixtures for Strategy Service tests."""

from unittest.mock import AsyncMock

import pytest

from shared.generated import classification_pb2, market_data_pb2, market_regime_pb2
from src.clients.classification_client import ClassificationClient
from src.clients.market_data_client import MarketDataClient
from src.clients.market_regime_client import MarketRegimeClient
from src.models import CandidateSymbol, RiskProfile, UserPreferences
from src.service import StrategyServicer
from src.utils.cache import UserCacheManager


@pytest.fixture
def mock_cache():
    """Mock UserCacheManager."""
    cache = AsyncMock(spec=UserCacheManager)
    cache.connect = AsyncMock()
    cache.get = AsyncMock(return_value=None)  # Default: cache miss
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    cache.close = AsyncMock()
    return cache


@pytest.fixture
def mock_regime_client():
    """Mock Market Regime Service client."""
    client = AsyncMock(spec=MarketRegimeClient)
    client.connect = AsyncMock()
    client.get_current_regime = AsyncMock(
        return_value=market_regime_pb2.GetCurrentRegimeResponse(
            regime="bull",
            confidence=0.85,
            timestamp="2024-01-15T10:00:00Z",
        )
    )
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_classification_client():
    """Mock Classification Service client."""
    client = AsyncMock(spec=ClassificationClient)
    client.connect = AsyncMock()

    # Mock get_candidate_symbols
    client.get_candidate_symbols = AsyncMock(
        return_value=(
            [
                CandidateSymbol(
                    symbol="AAPL",
                    sector="Technology",
                    theme="AI Infrastructure",
                    preliminary_score=85.0,
                ),
                CandidateSymbol(
                    symbol="MSFT",
                    sector="Technology",
                    theme="Cloud Computing",
                    preliminary_score=82.0,
                ),
                CandidateSymbol(
                    symbol="NVDA",
                    sector="Technology",
                    theme="AI Infrastructure",
                    preliminary_score=88.0,
                ),
            ],
            ["Technology"],
            ["AI Infrastructure", "Cloud Computing"],
        )
    )

    # Mock get_sector_analysis
    client.get_sector_analysis = AsyncMock(
        return_value=classification_pb2.GetSectorAnalysisResponse(
            sectors=[
                classification_pb2.SectorScore(
                    sector="Technology",
                    score=85.0,
                    rationale="Strong growth",
                    selected=True,
                ),
            ],
            regime="bull",
            cached_at="2024-01-15T10:00:00Z",
        )
    )

    # Mock get_thematic_analysis
    client.get_thematic_analysis = AsyncMock(
        return_value=classification_pb2.GetThematicAnalysisResponse(
            themes=[
                classification_pb2.ThemeScore(
                    theme="AI Infrastructure",
                    sector="Technology",
                    score=88.0,
                    rationale="Leading AI trend",
                    representative_symbols=["NVDA", "AAPL"],
                ),
                classification_pb2.ThemeScore(
                    theme="Cloud Computing",
                    sector="Technology",
                    score=82.0,
                    rationale="Cloud adoption growing",
                    representative_symbols=["MSFT"],
                ),
            ],
            cached_at="2024-01-15T10:00:00Z",
        )
    )

    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_market_data_client():
    """Mock Market Data Service client."""
    client = AsyncMock(spec=MarketDataClient)
    client.connect = AsyncMock()

    # Mock OHLCV data
    mock_ohlcv = [
        {
            "timestamp": f"2024-01-{i:02d}T00:00:00Z",
            "open": 150.0 + i,
            "high": 152.0 + i,
            "low": 148.0 + i,
            "close": 151.0 + i,
            "volume": 10_000_000 + i * 100_000,
            "adj_close": 151.0 + i,
        }
        for i in range(1, 61)  # 60 days of data
    ]

    client.get_ohlcv = AsyncMock(return_value=mock_ohlcv)

    # Mock stock info
    client.get_stock_info = AsyncMock(
        return_value=market_data_pb2.GetStockInfoResponse(
            symbol="AAPL",
            name="Apple Inc.",
            sector="Technology",
            industry="Consumer Electronics",
            exchange="NASDAQ",
            currency="USD",
            market_cap=3_000_000_000_000,
        )
    )

    client.close = AsyncMock()
    return client


@pytest.fixture
def strategy_service(
    mock_classification_client, mock_market_data_client, mock_regime_client, mock_cache
):
    """Create StrategyServicer with mocked dependencies."""
    return StrategyServicer(
        classification_client=mock_classification_client,
        market_data_client=mock_market_data_client,
        regime_client=mock_regime_client,
        cache_manager=mock_cache,
    )


@pytest.fixture
def default_preferences():
    """Default user preferences."""
    return UserPreferences(
        user_id="test_user",
        risk_profile=RiskProfile.MODERATE,
        preferred_sectors=[],
        excluded_sectors=[],
        max_single_position=0.10,
    )
