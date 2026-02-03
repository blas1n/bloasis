"""Pytest configuration and fixtures for Classification Service tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.clients.fingpt_client import MockFinGPTClient
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

    # Mock GetCurrentRegime response
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
def mock_fingpt_client():
    """Use real MockFinGPTClient for testing."""
    return MockFinGPTClient()


@pytest.fixture
def classification_service(mock_fingpt_client, mock_regime_client, mock_cache):
    """Create Classification Service with mocked dependencies."""
    return ClassificationService(
        fingpt_client=mock_fingpt_client,
        regime_client=mock_regime_client,
        cache_manager=mock_cache,
    )
