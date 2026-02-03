"""Unit tests for Factor Scoring Engine."""

from decimal import Decimal

import pytest

from src.factor_scoring import FACTOR_WEIGHTS, FactorScoringEngine
from src.models import FactorScores, RiskProfile


@pytest.fixture
def factor_engine(mock_market_data_client):
    """Create FactorScoringEngine with mocked market data client."""
    return FactorScoringEngine(mock_market_data_client)


@pytest.mark.asyncio
async def test_calculate_factor_scores(factor_engine):
    """Test calculating all 6 factor scores."""
    symbol = "AAPL"
    regime = "bull"

    scores = await factor_engine.calculate_factor_scores(symbol, regime)

    # Verify all factors are present
    assert isinstance(scores, FactorScores)
    assert 0 <= scores.momentum <= 100
    assert 0 <= scores.value <= 100
    assert 0 <= scores.quality <= 100
    assert 0 <= scores.volatility <= 100
    assert 0 <= scores.liquidity <= 100
    assert 0 <= scores.sentiment <= 100


def test_calculate_final_score_conservative(factor_engine):
    """Test final score calculation with conservative profile."""
    factor_scores = FactorScores(
        momentum=70.0,
        value=80.0,
        quality=85.0,
        volatility=75.0,
        liquidity=65.0,
        sentiment=60.0,
    )

    final_score = factor_engine.calculate_final_score(factor_scores, RiskProfile.CONSERVATIVE)

    # Verify score is Decimal and in valid range
    assert isinstance(final_score, Decimal)
    assert Decimal("0") <= final_score <= Decimal("100")

    # Conservative should weight quality and value heavily
    weights = FACTOR_WEIGHTS[RiskProfile.CONSERVATIVE]
    expected = (
        Decimal("70.0") * Decimal(str(weights["momentum"]))
        + Decimal("80.0") * Decimal(str(weights["value"]))
        + Decimal("85.0") * Decimal(str(weights["quality"]))
        + Decimal("75.0") * Decimal(str(weights["volatility"]))
        + Decimal("65.0") * Decimal(str(weights["liquidity"]))
        + Decimal("60.0") * Decimal(str(weights["sentiment"]))
    ).quantize(Decimal("0.01"))

    assert final_score == expected


def test_calculate_final_score_moderate(factor_engine):
    """Test final score calculation with moderate profile."""
    factor_scores = FactorScores(
        momentum=70.0,
        value=80.0,
        quality=85.0,
        volatility=75.0,
        liquidity=65.0,
        sentiment=60.0,
    )

    final_score = factor_engine.calculate_final_score(factor_scores, RiskProfile.MODERATE)

    # Verify score is Decimal and in valid range
    assert isinstance(final_score, Decimal)
    assert Decimal("0") <= final_score <= Decimal("100")


def test_calculate_final_score_aggressive(factor_engine):
    """Test final score calculation with aggressive profile."""
    factor_scores = FactorScores(
        momentum=90.0,
        value=60.0,
        quality=70.0,
        volatility=50.0,
        liquidity=65.0,
        sentiment=85.0,
    )

    final_score = factor_engine.calculate_final_score(factor_scores, RiskProfile.AGGRESSIVE)

    # Aggressive should weight momentum and sentiment heavily
    weights = FACTOR_WEIGHTS[RiskProfile.AGGRESSIVE]
    expected = (
        Decimal("90.0") * Decimal(str(weights["momentum"]))
        + Decimal("60.0") * Decimal(str(weights["value"]))
        + Decimal("70.0") * Decimal(str(weights["quality"]))
        + Decimal("50.0") * Decimal(str(weights["volatility"]))
        + Decimal("65.0") * Decimal(str(weights["liquidity"]))
        + Decimal("85.0") * Decimal(str(weights["sentiment"]))
    ).quantize(Decimal("0.01"))

    assert final_score == expected


def test_calculate_momentum_uptrend(factor_engine):
    """Test momentum calculation with uptrend."""
    # Create OHLCV data with uptrend
    ohlcv = [{"close": 100.0 + i} for i in range(30)]

    momentum = factor_engine._calculate_momentum(ohlcv)

    # Uptrend should have momentum > 50
    assert momentum > 50
    assert 0 <= momentum <= 100


def test_calculate_momentum_downtrend(factor_engine):
    """Test momentum calculation with downtrend."""
    # Create OHLCV data with downtrend
    ohlcv = [{"close": 200.0 - i} for i in range(30)]

    momentum = factor_engine._calculate_momentum(ohlcv)

    # Downtrend should have momentum < 50
    assert momentum < 50
    assert 0 <= momentum <= 100


def test_calculate_momentum_insufficient_data(factor_engine):
    """Test momentum calculation with insufficient data."""
    ohlcv = [{"close": 100.0} for _ in range(10)]  # Less than 20 bars

    momentum = factor_engine._calculate_momentum(ohlcv)

    # Should return neutral score
    assert momentum == 50.0


def test_calculate_volatility_low(factor_engine):
    """Test volatility calculation with low volatility."""
    # Create OHLCV data with low volatility (stable prices)
    ohlcv = [{"close": 100.0 + (i % 2) * 0.1} for i in range(30)]

    volatility = factor_engine._calculate_volatility(ohlcv)

    # Low volatility should have high score (inverse)
    assert volatility > 70
    assert 0 <= volatility <= 100


def test_calculate_volatility_high(factor_engine):
    """Test volatility calculation with high volatility."""
    # Create OHLCV data with high volatility (large swings)
    ohlcv = [{"close": 100.0 + (i % 2) * 10} for i in range(30)]

    volatility = factor_engine._calculate_volatility(ohlcv)

    # High volatility should have low score (inverse)
    assert volatility < 50
    assert 0 <= volatility <= 100


def test_calculate_volatility_insufficient_data(factor_engine):
    """Test volatility calculation with insufficient data."""
    ohlcv = [{"close": 100.0} for _ in range(10)]

    volatility = factor_engine._calculate_volatility(ohlcv)

    # Should return neutral score
    assert volatility == 50.0


def test_calculate_liquidity_high_volume(factor_engine):
    """Test liquidity calculation with high volume."""
    # Create OHLCV data with high volume
    ohlcv = [{"volume": 5_000_000} for _ in range(30)]

    liquidity = factor_engine._calculate_liquidity(ohlcv)

    # High volume should have high score
    assert liquidity > 80
    assert 0 <= liquidity <= 100


def test_calculate_liquidity_low_volume(factor_engine):
    """Test liquidity calculation with low volume."""
    # Create OHLCV data with low volume
    ohlcv = [{"volume": 100_000} for _ in range(30)]

    liquidity = factor_engine._calculate_liquidity(ohlcv)

    # Low volume should have low score
    assert liquidity < 20
    assert 0 <= liquidity <= 100


def test_calculate_liquidity_capped_at_100(factor_engine):
    """Test liquidity calculation caps at 100."""
    # Create OHLCV data with very high volume
    ohlcv = [{"volume": 50_000_000} for _ in range(30)]

    liquidity = factor_engine._calculate_liquidity(ohlcv)

    # Should cap at 100
    assert liquidity == 100.0


def test_calculate_liquidity_insufficient_data(factor_engine):
    """Test liquidity calculation with insufficient data."""
    ohlcv = [{"volume": 1_000_000} for _ in range(10)]

    liquidity = factor_engine._calculate_liquidity(ohlcv)

    # Should return neutral score
    assert liquidity == 50.0


@pytest.mark.asyncio
async def test_calculate_value_placeholder(factor_engine):
    """Test value calculation (placeholder)."""
    value = await factor_engine._calculate_value("AAPL")

    # Should return neutral score (placeholder)
    assert value == 50.0


@pytest.mark.asyncio
async def test_calculate_quality_placeholder(factor_engine):
    """Test quality calculation (placeholder)."""
    quality = await factor_engine._calculate_quality("AAPL")

    # Should return neutral score (placeholder)
    assert quality == 50.0


@pytest.mark.asyncio
async def test_calculate_sentiment_placeholder(factor_engine):
    """Test sentiment calculation (placeholder)."""
    sentiment = await factor_engine._calculate_sentiment("AAPL")

    # Should return neutral score (placeholder)
    assert sentiment == 50.0


def test_factor_weights_sum_to_one():
    """Test that factor weights for each profile sum to 1.0."""
    for profile, weights in FACTOR_WEIGHTS.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"{profile} weights sum to {total}, not 1.0"


def test_factor_weights_profiles_exist():
    """Test that all risk profiles have weights defined."""
    assert RiskProfile.CONSERVATIVE in FACTOR_WEIGHTS
    assert RiskProfile.MODERATE in FACTOR_WEIGHTS
    assert RiskProfile.AGGRESSIVE in FACTOR_WEIGHTS


def test_factor_weights_all_factors():
    """Test that all profiles have all 6 factors defined."""
    expected_factors = {"momentum", "value", "quality", "volatility", "liquidity", "sentiment"}

    for profile, weights in FACTOR_WEIGHTS.items():
        assert set(weights.keys()) == expected_factors, f"{profile} missing factors"
