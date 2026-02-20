"""Integration tests for Classification Service gRPC endpoints.

Tests actual gRPC communication (with mocked external dependencies).
"""

from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest
from shared.generated import classification_pb2

from src.clients.market_regime_client import MarketRegimeClient
from src.service import ClassificationService, ClassificationServicer
from src.utils.cache import CacheManager


def _make_mock_analyst():
    """Create a mock Claude analyst with realistic sector/theme responses."""
    analyst = AsyncMock()
    analyst.analyze = AsyncMock(side_effect=_analyst_side_effect)
    return analyst


def _analyst_side_effect(**kwargs) -> dict:
    """Return appropriate mock data based on prompt content."""
    prompt = kwargs.get("prompt", "")
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
async def grpc_servicer():
    """Create gRPC servicer with mocked dependencies."""
    # Mock cache
    mock_cache = AsyncMock(spec=CacheManager)
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(return_value=True)
    mock_cache.connect = AsyncMock()
    mock_cache.close = AsyncMock()

    # Mock regime client
    mock_regime_client = AsyncMock(spec=MarketRegimeClient)
    mock_response = MagicMock()
    mock_response.regime = "bull"
    mock_response.confidence = 0.85
    mock_response.timestamp = "2026-02-02T12:00:00Z"
    mock_regime_client.get_current_regime = AsyncMock(return_value=mock_response)

    # Create service and servicer with mock Claude analyst
    service = ClassificationService(
        analyst=_make_mock_analyst(),
        regime_client=mock_regime_client,
        cache_manager=mock_cache,
    )
    return ClassificationServicer(service)


@pytest.fixture
def grpc_context():
    """Create mock gRPC context."""
    context = MagicMock(spec=grpc.aio.ServicerContext)
    context.set_code = MagicMock()
    context.set_details = MagicMock()
    return context


@pytest.mark.asyncio
class TestGetSectorAnalysisRPC:
    """Test GetSectorAnalysis gRPC endpoint."""

    async def test_get_sector_analysis_success(self, grpc_servicer, grpc_context):
        """Test successful sector analysis request."""
        request = classification_pb2.GetSectorAnalysisRequest(
            regime="bull",
            force_refresh=False,
        )

        response = await grpc_servicer.GetSectorAnalysis(request, grpc_context)

        # Verify response structure
        assert isinstance(response, classification_pb2.GetSectorAnalysisResponse)
        assert response.regime == "bull"
        assert len(response.sectors) == 11  # Mock returns all 11 GICS sectors
        assert any(s.selected for s in response.sectors)
        assert response.cached_at  # Timestamp present

        # Verify no errors
        grpc_context.set_code.assert_not_called()

    async def test_get_sector_analysis_missing_regime(self, grpc_servicer, grpc_context):
        """Test request with missing regime field."""
        request = classification_pb2.GetSectorAnalysisRequest(
            regime="",  # Empty regime
            force_refresh=False,
        )

        await grpc_servicer.GetSectorAnalysis(request, grpc_context)

        # Verify error
        grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
        grpc_context.set_details.assert_called_once()
        assert "regime" in grpc_context.set_details.call_args[0][0].lower()

    async def test_get_sector_analysis_force_refresh(self, grpc_servicer, grpc_context):
        """Test sector analysis with force_refresh=True."""
        request = classification_pb2.GetSectorAnalysisRequest(
            regime="crisis",
            force_refresh=True,
        )

        response = await grpc_servicer.GetSectorAnalysis(request, grpc_context)

        # Verify response structure (sector selection logic is tested in unit tests)
        assert response.regime == "crisis"
        assert len(response.sectors) == 11
        assert any(s.selected for s in response.sectors)


@pytest.mark.asyncio
class TestGetThematicAnalysisRPC:
    """Test GetThematicAnalysis gRPC endpoint."""

    async def test_get_thematic_analysis_success(self, grpc_servicer, grpc_context):
        """Test successful thematic analysis request."""
        request = classification_pb2.GetThematicAnalysisRequest(
            sectors=["Technology", "Healthcare"],
            regime="bull",
            force_refresh=False,
        )

        response = await grpc_servicer.GetThematicAnalysis(request, grpc_context)

        # Verify response
        assert isinstance(response, classification_pb2.GetThematicAnalysisResponse)
        assert len(response.themes) > 0
        assert all(t.sector in ["Technology", "Healthcare"] for t in response.themes)
        assert all(len(t.representative_symbols) > 0 for t in response.themes)
        assert response.cached_at

        # Verify themes are sorted by score
        scores = [t.score for t in response.themes]
        assert scores == sorted(scores, reverse=True)

    async def test_get_thematic_analysis_missing_sectors(self, grpc_servicer, grpc_context):
        """Test request with missing sectors field."""
        request = classification_pb2.GetThematicAnalysisRequest(
            sectors=[],  # Empty sectors
            regime="bull",
            force_refresh=False,
        )

        await grpc_servicer.GetThematicAnalysis(request, grpc_context)

        # Verify error
        grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
        grpc_context.set_details.assert_called_once()
        assert "sectors" in grpc_context.set_details.call_args[0][0].lower()

    async def test_get_thematic_analysis_missing_regime(self, grpc_servicer, grpc_context):
        """Test request with missing regime field."""
        request = classification_pb2.GetThematicAnalysisRequest(
            sectors=["Technology"],
            regime="",  # Empty regime
            force_refresh=False,
        )

        await grpc_servicer.GetThematicAnalysis(request, grpc_context)

        # Verify error
        grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)


@pytest.mark.asyncio
class TestGetCandidateSymbolsRPC:
    """Test GetCandidateSymbols gRPC endpoint."""

    async def test_get_candidate_symbols_success(self, grpc_servicer, grpc_context):
        """Test successful candidate symbols request."""
        request = classification_pb2.GetCandidateSymbolsRequest(
            regime="bull",
            max_candidates=50,
            force_refresh=False,
        )

        response = await grpc_servicer.GetCandidateSymbols(request, grpc_context)

        # Verify response
        assert isinstance(response, classification_pb2.GetCandidateSymbolsResponse)
        assert len(response.candidates) > 0
        assert len(response.candidates) <= 50
        assert len(response.selected_sectors) > 0
        assert len(response.top_themes) > 0
        assert response.regime == "bull"

        # Verify candidates structure
        for candidate in response.candidates:
            assert candidate.symbol
            assert candidate.sector in response.selected_sectors
            assert candidate.theme
            assert 0 <= candidate.preliminary_score <= 100

    async def test_get_candidate_symbols_without_regime(self, grpc_servicer, grpc_context):
        """Test candidate symbols fetches regime from Market Regime Service."""
        request = classification_pb2.GetCandidateSymbolsRequest(
            regime="",  # Empty - should fetch from service
            max_candidates=30,
            force_refresh=False,
        )

        response = await grpc_servicer.GetCandidateSymbols(request, grpc_context)

        # Verify: should use regime from Market Regime Service
        assert response.regime == "bull"  # From mock
        assert len(response.candidates) > 0
        assert len(response.candidates) <= 30

    async def test_get_candidate_symbols_max_limit(self, grpc_servicer, grpc_context):
        """Test max_candidates limit is respected."""
        request = classification_pb2.GetCandidateSymbolsRequest(
            regime="bull",
            max_candidates=10,
            force_refresh=False,
        )

        response = await grpc_servicer.GetCandidateSymbols(request, grpc_context)

        # Verify limit
        assert len(response.candidates) <= 10

    async def test_get_candidate_symbols_default_max(self, grpc_servicer, grpc_context):
        """Test default max_candidates (50) is used when not specified."""
        request = classification_pb2.GetCandidateSymbolsRequest(
            regime="bull",
            max_candidates=0,  # 0 means use default
            force_refresh=False,
        )

        response = await grpc_servicer.GetCandidateSymbols(request, grpc_context)

        # Verify: should use default of 50
        assert len(response.candidates) <= 50


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in gRPC endpoints."""

    async def test_market_regime_service_unavailable(self):
        """Test handling when Market Regime Service is unavailable."""
        # Setup: regime client that raises ConnectionError
        mock_cache = AsyncMock(spec=CacheManager)
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)

        mock_regime_client = AsyncMock(spec=MarketRegimeClient)
        mock_regime_client.get_current_regime = AsyncMock(
            side_effect=ConnectionError("Service unavailable")
        )

        service = ClassificationService(
            analyst=_make_mock_analyst(),
            regime_client=mock_regime_client,
            cache_manager=mock_cache,
        )
        servicer = ClassificationServicer(service)

        # Execute
        context = MagicMock(spec=grpc.aio.ServicerContext)
        context.set_code = MagicMock()
        context.set_details = MagicMock()

        request = classification_pb2.GetCandidateSymbolsRequest(
            regime="",  # Empty - will try to fetch from service
            max_candidates=50,
        )

        await servicer.GetCandidateSymbols(request, context)

        # Verify error handling
        context.set_code.assert_called_once_with(grpc.StatusCode.UNAVAILABLE)
        context.set_details.assert_called_once()

    async def test_market_regime_service_timeout(self):
        """Test handling when Market Regime Service times out."""
        # Setup: regime client that raises TimeoutError
        mock_cache = AsyncMock(spec=CacheManager)
        mock_cache.get = AsyncMock(return_value=None)

        mock_regime_client = AsyncMock(spec=MarketRegimeClient)
        mock_regime_client.get_current_regime = AsyncMock(
            side_effect=TimeoutError("Request timed out")
        )

        service = ClassificationService(
            analyst=_make_mock_analyst(),
            regime_client=mock_regime_client,
            cache_manager=mock_cache,
        )
        servicer = ClassificationServicer(service)

        # Execute
        context = MagicMock(spec=grpc.aio.ServicerContext)
        context.set_code = MagicMock()
        context.set_details = MagicMock()

        request = classification_pb2.GetCandidateSymbolsRequest(regime="")

        await servicer.GetCandidateSymbols(request, context)

        # Verify error handling
        context.set_code.assert_called_once_with(grpc.StatusCode.DEADLINE_EXCEEDED)
