"""Unit tests for Factor Scoring Engine."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.factor_scoring import FACTOR_WEIGHTS, REGIME_MULTIPLIERS, FactorScoringEngine
from src.models import FactorScores, RiskProfile


@pytest.fixture
def factor_engine(mock_market_data_client):
    """Create FactorScoringEngine with mocked market data client."""
    return FactorScoringEngine(mock_market_data_client)


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for caching."""
    from shared.utils.redis_client import RedisClient

    client = AsyncMock(spec=RedisClient)
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.get = AsyncMock(return_value=None)  # Default: cache miss
    client.setex = AsyncMock()
    return client


@pytest.fixture
def factor_engine_with_redis(mock_market_data_client, mock_redis_client):
    """Create FactorScoringEngine with Redis client for caching tests."""
    return FactorScoringEngine(
        market_data_client=mock_market_data_client,
        redis_client=mock_redis_client,
    )


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

    # Conservative weights quality and value heavily — score should reflect that
    assert final_score > Decimal("70")  # Quality(85) and Value(80) are high


def test_calculate_final_score_conservative_no_regime(factor_engine):
    """Test final score without regime uses normal_bull default."""
    factor_scores = FactorScores(
        momentum=70.0,
        value=80.0,
        quality=85.0,
        volatility=75.0,
        liquidity=65.0,
        sentiment=60.0,
    )

    # Default regime is normal_bull
    score_default = factor_engine.calculate_final_score(
        factor_scores, RiskProfile.CONSERVATIVE
    )
    score_explicit = factor_engine.calculate_final_score(
        factor_scores, RiskProfile.CONSERVATIVE, "normal_bull"
    )

    assert score_default == score_explicit


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

    assert isinstance(final_score, Decimal)
    assert Decimal("0") <= final_score <= Decimal("100")

    # Aggressive in normal_bull should boost momentum + sentiment
    # High momentum(90) and sentiment(85) should push score up
    assert final_score > Decimal("70")


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
async def test_calculate_value_optimal_pe(factor_engine, mock_market_data_client):
    """Test value with P/E near optimal (PE=12 peak)."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
        pe_ratio=12.0,
        profit_margin=0.20,
        current_ratio=1.5,
    )

    value = await factor_engine._calculate_value("AAPL")
    # PE=12 → peak score ~100, PM=20% → 100, CR=1.5 → 75
    # 100*0.4 + 100*0.3 + 75*0.3 = 92.5
    assert value > 85.0


@pytest.mark.asyncio
async def test_calculate_value_high_pe(factor_engine, mock_market_data_client):
    """Test value with high P/E (expensive stock)."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="EXPS",
        name="Expensive Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
        pe_ratio=40.0,
        profit_margin=0.05,
        current_ratio=0.8,
    )

    value = await factor_engine._calculate_value("EXPS")
    # PE=40 → low gaussian score, PM=5% → 25, CR=0.8 → 40
    assert value < 40.0


@pytest.mark.asyncio
async def test_calculate_value_negative_pe(factor_engine, mock_market_data_client):
    """Test value with negative P/E (losses)."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="LOSS",
        name="Loss Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=1_000_000_000,
        pe_ratio=-5.0,
    )

    value = await factor_engine._calculate_value("LOSS")
    # Negative PE → 30, rest neutral (50 each)
    assert 30.0 <= value <= 45.0


@pytest.mark.asyncio
async def test_calculate_value_missing_all_fields(factor_engine, mock_market_data_client):
    """Test value when no optional fields are set."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
    )

    value = await factor_engine._calculate_value("AAPL")
    assert value == 50.0  # All neutral


@pytest.mark.asyncio
async def test_calculate_value_api_error(factor_engine, mock_market_data_client):
    """Test value calculation when API call fails."""
    mock_market_data_client.get_stock_info.side_effect = Exception("API Error")

    value = await factor_engine._calculate_value("AAPL")
    assert value == 50.0


@pytest.mark.asyncio
async def test_calculate_value_high_current_ratio(factor_engine, mock_market_data_client):
    """Test value with very high current ratio (idle assets)."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="CASH",
        name="Cash Inc.",
        sector="Technology",
        industry="Software",
        exchange="NASDAQ",
        currency="USD",
        market_cap=1_000_000_000,
        pe_ratio=12.0,
        current_ratio=5.0,  # Too high → idle assets
    )

    value = await factor_engine._calculate_value("CASH")
    # CR=5.0 → max(40, 100 - (5-2)*15) = max(40, 55) = 55
    # Still reasonable but not top score
    assert 50.0 <= value <= 80.0


@pytest.mark.asyncio
async def test_calculate_quality_excellent_fundamentals(factor_engine, mock_market_data_client):
    """Test quality with excellent all-around fundamentals."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
        return_on_equity=0.25,  # 25% ROE → 100
        debt_to_equity=0.5,  # 0.5 D/E → 75
        profit_margin=0.25,  # 25% → 100
        current_ratio=1.5,  # 1.5 → 75
    )

    quality = await factor_engine._calculate_quality("AAPL")
    # ROE: 100*0.25 + D/E: 75*0.20 + PM: 100*0.25 + CR: 75*0.15 + Cap: 90*0.15
    # = 25 + 15 + 25 + 11.25 + 13.5 = 89.75
    assert quality > 85.0


@pytest.mark.asyncio
async def test_calculate_quality_poor_fundamentals(factor_engine, mock_market_data_client):
    """Test quality with poor fundamentals."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="DEBT",
        name="High Debt Inc.",
        sector="Technology",
        industry="Software",
        exchange="NASDAQ",
        currency="USD",
        market_cap=50_000_000_000,
        return_on_equity=0.03,  # 3% ROE → 12
        debt_to_equity=2.0,  # 2.0 D/E → 0
        profit_margin=0.02,  # 2% → 8
        current_ratio=0.5,  # 0.5 → 25
    )

    quality = await factor_engine._calculate_quality("DEBT")
    assert quality < 30.0


@pytest.mark.asyncio
async def test_calculate_quality_missing_fundamentals(factor_engine, mock_market_data_client):
    """Test quality with missing optional fields (uses neutral)."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="MID",
        name="Mid Cap Inc.",
        sector="Technology",
        industry="Software",
        exchange="NASDAQ",
        currency="USD",
        market_cap=50_000_000_000,
    )

    quality = await factor_engine._calculate_quality("MID")
    # All neutral (50) except cap which is ~58.89
    # 50*0.25 + 50*0.20 + 50*0.25 + 50*0.15 + 58.89*0.15 ≈ 51.33
    assert 49.0 <= quality <= 55.0


@pytest.mark.asyncio
async def test_calculate_quality_api_error(factor_engine, mock_market_data_client):
    """Test quality when API call fails."""
    mock_market_data_client.get_stock_info.side_effect = Exception("API Error")

    quality = await factor_engine._calculate_quality("AAPL")
    assert quality == 50.0


@pytest.mark.asyncio
async def test_calculate_quality_negative_roe(factor_engine, mock_market_data_client):
    """Test quality with negative ROE."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="LOSS",
        name="Loss Inc.",
        sector="Technology",
        industry="Software",
        exchange="NASDAQ",
        currency="USD",
        market_cap=10_000_000_000,
        return_on_equity=-0.10,  # Negative ROE
        debt_to_equity=1.5,
        profit_margin=-0.05,  # Negative margin
        current_ratio=0.8,
    )

    quality = await factor_engine._calculate_quality("LOSS")
    # Poor fundamentals
    assert quality < 35.0


@pytest.mark.asyncio
async def test_calculate_sentiment_high_momentum(factor_engine, mock_market_data_client):
    """Test sentiment calculation with high momentum (bullish)."""
    # Create OHLCV data with strong uptrend (high momentum)
    mock_ohlcv = [
        {
            "timestamp": f"2024-01-{i:02d}T00:00:00Z",
            "open": 100.0 + i * 2,
            "high": 102.0 + i * 2,
            "low": 98.0 + i * 2,
            "close": 100.0 + i * 2,  # Strong uptrend
            "volume": 10_000_000,
            "adj_close": 100.0 + i * 2,
        }
        for i in range(1, 31)
    ]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine._calculate_sentiment("AAPL")
    # High momentum should map to bullish sentiment (60-80)
    assert 60.0 <= sentiment <= 80.0


@pytest.mark.asyncio
async def test_calculate_sentiment_low_momentum(factor_engine, mock_market_data_client):
    """Test sentiment calculation with low momentum (bearish)."""
    # Create OHLCV data with strong downtrend (low momentum)
    mock_ohlcv = [
        {
            "timestamp": f"2024-01-{i:02d}T00:00:00Z",
            "open": 200.0 - i * 3,
            "high": 202.0 - i * 3,
            "low": 198.0 - i * 3,
            "close": 200.0 - i * 3,  # Strong downtrend
            "volume": 10_000_000,
            "adj_close": 200.0 - i * 3,
        }
        for i in range(1, 31)
    ]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine._calculate_sentiment("AAPL")
    # Low momentum should map to bearish sentiment (20-40)
    assert 20.0 <= sentiment <= 40.0


@pytest.mark.asyncio
async def test_calculate_sentiment_neutral_momentum(factor_engine, mock_market_data_client):
    """Test sentiment calculation with neutral momentum."""
    # Create OHLCV data with sideways movement (neutral momentum)
    mock_ohlcv = [
        {
            "timestamp": f"2024-01-{i:02d}T00:00:00Z",
            "open": 150.0,
            "high": 151.0,
            "low": 149.0,
            "close": 150.0 + (i % 3) - 1,  # Slight variation around 150
            "volume": 10_000_000,
            "adj_close": 150.0,
        }
        for i in range(1, 31)
    ]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine._calculate_sentiment("AAPL")
    # Neutral momentum should map to neutral sentiment (40-60)
    assert 40.0 <= sentiment <= 60.0


@pytest.mark.asyncio
async def test_calculate_sentiment_api_error(factor_engine, mock_market_data_client):
    """Test sentiment calculation when API call fails."""
    mock_market_data_client.get_ohlcv.side_effect = Exception("API Error")

    sentiment = await factor_engine._calculate_sentiment("AAPL")
    assert sentiment == 50.0  # Fallback to neutral


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


# Sentiment caching tests


@pytest.mark.asyncio
async def test_calculate_sentiment_uses_cache(
    factor_engine_with_redis, mock_redis_client
):
    """Test that cached sentiment is used when available."""
    # Redis returns cached value
    mock_redis_client.get.return_value = 75.0

    sentiment = await factor_engine_with_redis._calculate_sentiment("AAPL")

    # Should use cached value
    assert sentiment == 75.0


@pytest.mark.asyncio
async def test_calculate_sentiment_from_momentum_directly(factor_engine, mock_market_data_client):
    """Test the _calculate_sentiment_from_momentum method directly."""
    # Create OHLCV data with downtrend
    mock_ohlcv = [{"close": 200.0 - i * 3, "volume": 1_000_000} for i in range(30)]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine._calculate_sentiment_from_momentum("AAPL")

    # Downtrend should give low sentiment (20-40)
    assert 20.0 <= sentiment <= 40.0


@pytest.mark.asyncio
async def test_get_cached_sentiment_handles_redis_error(
    factor_engine_with_redis, mock_redis_client, mock_market_data_client
):
    """Test that cache retrieval errors fall back to momentum proxy."""
    mock_redis_client.get.side_effect = Exception("Redis connection error")

    # Mock OHLCV data for momentum fallback (neutral)
    mock_ohlcv = [{"close": 150.0, "volume": 1_000_000} for _ in range(30)]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine_with_redis._calculate_sentiment("AAPL")

    # Should fall back to momentum proxy (neutral)
    assert 40.0 <= sentiment <= 60.0


# --- Regime-Adaptive Factor Weight Tests ---


def test_regime_multipliers_all_regimes_have_all_factors():
    """Every regime should define multipliers for all 6 factors."""
    expected_factors = {"momentum", "value", "quality", "volatility", "liquidity", "sentiment"}

    for regime, mults in REGIME_MULTIPLIERS.items():
        assert set(mults.keys()) == expected_factors, f"{regime} missing factors"


def test_crisis_regime_boosts_quality_and_volatility(factor_engine):
    """In crisis regime, quality and volatility should be weighted much higher."""
    scores = FactorScores(
        momentum=50.0,
        value=50.0,
        quality=90.0,  # High quality
        volatility=90.0,  # Low volatility (inverse score)
        liquidity=50.0,
        sentiment=50.0,
    )

    score_crisis = factor_engine.calculate_final_score(
        scores, RiskProfile.MODERATE, "crisis"
    )
    score_bull = factor_engine.calculate_final_score(
        scores, RiskProfile.MODERATE, "normal_bull"
    )

    # Crisis should reward quality/volatility more than bull
    assert score_crisis > score_bull


def test_bull_regime_boosts_momentum(factor_engine):
    """In bull regime, momentum should be weighted higher."""
    scores = FactorScores(
        momentum=90.0,  # High momentum
        value=50.0,
        quality=50.0,
        volatility=50.0,
        liquidity=50.0,
        sentiment=50.0,
    )

    score_bull = factor_engine.calculate_final_score(
        scores, RiskProfile.MODERATE, "normal_bull"
    )
    score_crisis = factor_engine.calculate_final_score(
        scores, RiskProfile.MODERATE, "crisis"
    )

    # Bull should reward momentum more than crisis
    assert score_bull > score_crisis


def test_regime_weights_are_normalized(factor_engine):
    """Regime-adjusted weights should be normalized to sum to 1.0."""
    # If we give equal scores to all factors, the final score should equal that score
    scores = FactorScores(
        momentum=60.0,
        value=60.0,
        quality=60.0,
        volatility=60.0,
        liquidity=60.0,
        sentiment=60.0,
    )

    for regime in REGIME_MULTIPLIERS:
        final = factor_engine.calculate_final_score(
            scores, RiskProfile.MODERATE, regime
        )
        # All factors equal → result should be 60.0 regardless of regime weights
        assert final == Decimal("60.00"), f"Failed for regime={regime}: {final}"


def test_unknown_regime_uses_base_weights(factor_engine):
    """Unknown regime falls back to base weights (no multipliers)."""
    scores = FactorScores(
        momentum=70.0,
        value=80.0,
        quality=85.0,
        volatility=75.0,
        liquidity=65.0,
        sentiment=60.0,
    )

    final = factor_engine.calculate_final_score(
        scores, RiskProfile.MODERATE, "unknown_regime"
    )

    # Should still produce a valid score using base weights (mult=1.0 for all)
    assert isinstance(final, Decimal)
    assert Decimal("0") <= final <= Decimal("100")
