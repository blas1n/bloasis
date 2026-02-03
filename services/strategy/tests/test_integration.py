"""Integration tests for Strategy Service.

Tests gRPC servicer with mocked dependencies.
"""

from unittest.mock import AsyncMock

import grpc
import pytest

from shared.generated import strategy_pb2


@pytest.fixture
def grpc_context():
    """Mock gRPC context."""
    context = AsyncMock(spec=grpc.aio.ServicerContext)
    return context


@pytest.mark.asyncio
async def test_get_stock_picks_grpc(strategy_service, grpc_context):
    """Test GetStockPicks gRPC method."""
    request = strategy_pb2.StockPicksRequest(user_id="test_user", max_picks=5)

    response = await strategy_service.GetStockPicks(request, grpc_context)

    # Verify response
    assert len(response.picks) <= 5
    assert response.regime == "bull"
    assert response.applied_preferences.user_id == "test_user"
    assert response.generated_at

    # Verify picks structure
    for pick in response.picks:
        assert pick.symbol
        assert pick.sector
        assert pick.theme
        assert pick.factor_scores
        assert 0 <= pick.final_score <= 100
        assert pick.rank >= 1
        assert pick.rationale


@pytest.mark.asyncio
async def test_get_stock_picks_missing_user_id(strategy_service, grpc_context):
    """Test GetStockPicks with missing user_id."""
    request = strategy_pb2.StockPicksRequest(user_id="", max_picks=5)

    response = await strategy_service.GetStockPicks(request, grpc_context)

    # Verify error handling
    grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
    grpc_context.set_details.assert_called_once_with("user_id field is required")
    assert len(response.picks) == 0


@pytest.mark.asyncio
async def test_get_personalized_strategy_grpc(strategy_service, grpc_context):
    """Test GetPersonalizedStrategy gRPC method."""
    request = strategy_pb2.StrategyRequest(user_id="test_user")

    response = await strategy_service.GetPersonalizedStrategy(request, grpc_context)

    # Verify response structure
    assert response.user_id == "test_user"
    assert response.regime == "bull"
    assert len(response.selected_sectors) > 0
    assert len(response.top_themes) > 0
    assert len(response.stock_picks) > 0
    assert response.preferences.user_id == "test_user"
    assert response.cached_at


@pytest.mark.asyncio
async def test_get_personalized_strategy_missing_user_id(strategy_service, grpc_context):
    """Test GetPersonalizedStrategy with missing user_id."""
    request = strategy_pb2.StrategyRequest(user_id="")

    await strategy_service.GetPersonalizedStrategy(request, grpc_context)

    # Verify error handling
    grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
    grpc_context.set_details.assert_called_once_with("user_id field is required")


@pytest.mark.asyncio
async def test_update_preferences_grpc(strategy_service, grpc_context):
    """Test UpdatePreferences gRPC method."""
    request = strategy_pb2.UpdatePreferencesRequest(
        user_id="test_user",
        risk_profile=strategy_pb2.CONSERVATIVE,
        preferred_sectors=["Utilities", "Healthcare"],
        excluded_sectors=["Energy"],
        max_single_position=0.08,
    )

    response = await strategy_service.UpdatePreferences(request, grpc_context)

    # Verify response
    assert response.success is True
    assert response.preferences.user_id == "test_user"
    assert response.preferences.risk_profile == strategy_pb2.CONSERVATIVE
    assert list(response.preferences.preferred_sectors) == ["Utilities", "Healthcare"]
    assert list(response.preferences.excluded_sectors) == ["Energy"]
    assert response.preferences.max_single_position == 0.08


@pytest.mark.asyncio
async def test_update_preferences_missing_user_id(strategy_service, grpc_context):
    """Test UpdatePreferences with missing user_id."""
    request = strategy_pb2.UpdatePreferencesRequest(
        user_id="",
        risk_profile=strategy_pb2.MODERATE,
    )

    response = await strategy_service.UpdatePreferences(request, grpc_context)

    # Verify error handling
    grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
    grpc_context.set_details.assert_called_once_with("user_id field is required")
    assert response.success is False


@pytest.mark.asyncio
async def test_get_preferences_grpc(strategy_service, grpc_context):
    """Test GetPreferences gRPC method."""
    request = strategy_pb2.GetPreferencesRequest(user_id="test_user")

    response = await strategy_service.GetPreferences(request, grpc_context)

    # Verify response (should return defaults)
    assert response.user_id == "test_user"
    assert response.risk_profile == strategy_pb2.MODERATE
    assert response.max_single_position == 0.10


@pytest.mark.asyncio
async def test_get_preferences_missing_user_id(strategy_service, grpc_context):
    """Test GetPreferences with missing user_id."""
    request = strategy_pb2.GetPreferencesRequest(user_id="")

    await strategy_service.GetPreferences(request, grpc_context)

    # Verify error handling
    grpc_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
    grpc_context.set_details.assert_called_once_with("user_id field is required")


@pytest.mark.asyncio
async def test_risk_profile_mapping(strategy_service, grpc_context):
    """Test risk profile enum mapping between proto and internal models."""
    # Test all risk profiles
    profiles = [
        (strategy_pb2.CONSERVATIVE, "CONSERVATIVE"),
        (strategy_pb2.MODERATE, "MODERATE"),
        (strategy_pb2.AGGRESSIVE, "AGGRESSIVE"),
    ]

    for proto_profile, expected_str in profiles:
        request = strategy_pb2.UpdatePreferencesRequest(
            user_id="test_user",
            risk_profile=proto_profile,
            max_single_position=0.10,
        )

        response = await strategy_service.UpdatePreferences(request, grpc_context)

        assert response.success is True
        assert response.preferences.risk_profile == proto_profile


@pytest.mark.asyncio
async def test_factor_scores_in_response(strategy_service, grpc_context):
    """Test that factor scores are properly included in response."""
    request = strategy_pb2.StockPicksRequest(user_id="test_user", max_picks=3)

    response = await strategy_service.GetStockPicks(request, grpc_context)

    # Verify factor scores exist for each pick
    for pick in response.picks:
        assert hasattr(pick.factor_scores, "momentum")
        assert hasattr(pick.factor_scores, "value")
        assert hasattr(pick.factor_scores, "quality")
        assert hasattr(pick.factor_scores, "volatility")
        assert hasattr(pick.factor_scores, "liquidity")
        assert hasattr(pick.factor_scores, "sentiment")

        # Verify all scores are in valid range
        assert 0 <= pick.factor_scores.momentum <= 100
        assert 0 <= pick.factor_scores.value <= 100
        assert 0 <= pick.factor_scores.quality <= 100
        assert 0 <= pick.factor_scores.volatility <= 100
        assert 0 <= pick.factor_scores.liquidity <= 100
        assert 0 <= pick.factor_scores.sentiment <= 100
