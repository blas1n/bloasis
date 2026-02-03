"""Unit tests for Strategy Service business logic."""

from unittest.mock import AsyncMock

import pytest

from src.models import RiskProfile, UserPreferences
from src.utils.cache import build_preferences_cache_key, build_strategy_cache_key


@pytest.mark.asyncio
async def test_get_stock_picks_success(strategy_service):
    """Test successful stock picks generation."""
    user_id = "test_user"
    max_picks = 3

    picks, regime, preferences = await strategy_service.get_stock_picks(user_id, max_picks)

    # Verify results
    assert len(picks) <= max_picks
    assert regime == "bull"
    assert preferences.user_id == user_id

    # Verify picks are ranked
    for i, pick in enumerate(picks):
        assert pick.rank == i + 1

    # Verify picks have all required fields
    for pick in picks:
        assert pick.symbol
        assert pick.sector
        assert pick.theme
        assert pick.factor_scores
        assert 0 <= pick.final_score <= 100
        assert pick.rationale


@pytest.mark.asyncio
async def test_get_stock_picks_with_excluded_sectors(strategy_service, mock_cache):
    """Test stock picks with excluded sectors."""
    user_id = "test_user"

    # Mock preferences with excluded sectors
    mock_cache.get = AsyncMock(
        return_value={
            "user_id": user_id,
            "risk_profile": "MODERATE",
            "preferred_sectors": [],
            "excluded_sectors": ["Technology"],
            "max_single_position": 0.10,
        }
    )

    picks, regime, preferences = await strategy_service.get_stock_picks(user_id, max_picks=10)

    # Verify no Technology sector stocks
    for pick in picks:
        assert pick.sector != "Technology"


@pytest.mark.asyncio
async def test_get_personalized_strategy_cache_miss(strategy_service, mock_cache):
    """Test personalized strategy generation (cache miss)."""
    user_id = "test_user"

    # Ensure cache miss
    mock_cache.get = AsyncMock(return_value=None)

    result, from_cache = await strategy_service.get_personalized_strategy(user_id)

    # Verify result structure
    assert result["user_id"] == user_id
    assert result["regime"] == "bull"
    assert "selected_sectors" in result
    assert "top_themes" in result
    assert "stock_picks" in result
    assert "preferences" in result
    assert result["from_cache"] is False
    assert from_cache is False

    # Verify cache was called to set result
    mock_cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_get_personalized_strategy_cache_hit(strategy_service, mock_cache):
    """Test personalized strategy retrieval (cache hit)."""
    user_id = "test_user"

    cached_strategy = {
        "user_id": user_id,
        "regime": "bull",
        "selected_sectors": ["Technology"],
        "top_themes": ["AI Infrastructure"],
        "stock_picks": [],
        "preferences": {
            "user_id": user_id,
            "risk_profile": "MODERATE",
            "preferred_sectors": [],
            "excluded_sectors": [],
            "max_single_position": 0.10,
        },
        "cached_at": "2024-01-15T10:00:00Z",
        "from_cache": False,
    }

    mock_cache.get = AsyncMock(return_value=cached_strategy)

    result, from_cache = await strategy_service.get_personalized_strategy(user_id)

    # Verify cache hit
    assert result["from_cache"] is True
    assert from_cache is True
    assert result["user_id"] == user_id

    # Verify cache was not set again
    mock_cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_get_preferences_default(strategy_service, mock_cache):
    """Test getting default preferences when none exist."""
    user_id = "test_user"

    # Ensure cache miss
    mock_cache.get = AsyncMock(return_value=None)

    preferences = await strategy_service.get_preferences(user_id)

    # Verify default values
    assert preferences.user_id == user_id
    assert preferences.risk_profile == RiskProfile.MODERATE
    assert preferences.preferred_sectors == []
    assert preferences.excluded_sectors == []
    assert preferences.max_single_position == 0.10


@pytest.mark.asyncio
async def test_get_preferences_cached(strategy_service, mock_cache):
    """Test getting cached preferences."""
    user_id = "test_user"

    cached_prefs = {
        "user_id": user_id,
        "risk_profile": "AGGRESSIVE",
        "preferred_sectors": ["Technology"],
        "excluded_sectors": ["Energy"],
        "max_single_position": 0.15,
    }

    mock_cache.get = AsyncMock(return_value=cached_prefs)

    preferences = await strategy_service.get_preferences(user_id)

    # Verify cached values
    assert preferences.user_id == user_id
    assert preferences.risk_profile == RiskProfile.AGGRESSIVE
    assert preferences.preferred_sectors == ["Technology"]
    assert preferences.excluded_sectors == ["Energy"]
    assert preferences.max_single_position == 0.15


@pytest.mark.asyncio
async def test_update_preferences(strategy_service, mock_cache):
    """Test updating user preferences."""
    user_id = "test_user"

    new_preferences = UserPreferences(
        user_id=user_id,
        risk_profile=RiskProfile.CONSERVATIVE,
        preferred_sectors=["Utilities"],
        excluded_sectors=["Technology"],
        max_single_position=0.08,
    )

    updated = await strategy_service.update_preferences(user_id, new_preferences)

    # Verify preferences were updated
    assert updated.user_id == user_id
    assert updated.risk_profile == RiskProfile.CONSERVATIVE

    # Verify cache operations
    pref_key = build_preferences_cache_key(user_id)
    strategy_key = build_strategy_cache_key(user_id)

    # Verify preferences were cached
    mock_cache.set.assert_called_once()
    call_args = mock_cache.set.call_args
    assert call_args[0][0] == pref_key

    # Verify strategy cache was invalidated
    mock_cache.delete.assert_called_once_with(strategy_key)


@pytest.mark.asyncio
async def test_generate_rationale_with_strengths(strategy_service):
    """Test rationale generation with strong factors."""
    from src.models import CandidateSymbol, FactorScores

    candidate = CandidateSymbol(
        symbol="AAPL",
        sector="Technology",
        theme="AI Infrastructure",
        preliminary_score=85.0,
    )

    factor_scores = FactorScores(
        momentum=75.0,
        value=80.0,
        quality=85.0,
        volatility=70.0,
        liquidity=90.0,
        sentiment=65.0,
    )

    rationale = strategy_service._generate_rationale(candidate, factor_scores)

    # Verify rationale mentions strengths
    assert "AAPL" in rationale
    assert "AI Infrastructure" in rationale
    assert "strong momentum" in rationale
    assert "attractive valuation" in rationale
    assert "high quality" in rationale
    assert "high liquidity" in rationale


@pytest.mark.asyncio
async def test_generate_rationale_balanced(strategy_service):
    """Test rationale generation with balanced factors."""
    from src.models import CandidateSymbol, FactorScores

    candidate = CandidateSymbol(
        symbol="MSFT",
        sector="Technology",
        theme="Cloud Computing",
        preliminary_score=70.0,
    )

    factor_scores = FactorScores(
        momentum=60.0,
        value=55.0,
        quality=65.0,
        volatility=50.0,
        liquidity=58.0,
        sentiment=62.0,
    )

    rationale = strategy_service._generate_rationale(candidate, factor_scores)

    # Verify balanced factors message
    assert "MSFT" in rationale
    assert "Cloud Computing" in rationale
    assert "balanced factors" in rationale


@pytest.mark.asyncio
async def test_stock_picks_sorting(strategy_service):
    """Test that stock picks are sorted by final score."""
    user_id = "test_user"

    picks, _, _ = await strategy_service.get_stock_picks(user_id, max_picks=10)

    # Verify picks are sorted descending by final_score
    for i in range(len(picks) - 1):
        assert picks[i].final_score >= picks[i + 1].final_score

    # Verify ranks are sequential
    for i, pick in enumerate(picks):
        assert pick.rank == i + 1
