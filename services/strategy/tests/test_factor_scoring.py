"""Unit tests for Factor Scoring Engine."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.factor_scoring import FACTOR_WEIGHTS, FactorScoringEngine
from src.models import FactorScores, RiskProfile


@pytest.fixture
def factor_engine(mock_market_data_client):
    """Create FactorScoringEngine with mocked market data client (no FinGPT)."""
    return FactorScoringEngine(mock_market_data_client)


@pytest.fixture
def mock_fingpt_client():
    """Mock FinGPT client for sentiment analysis."""
    from src.clients.fingpt_client import FinGPTClient

    client = AsyncMock(spec=FinGPTClient)
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.analyze_sentiment = AsyncMock(
        return_value={
            "sentiment": 0.6,
            "confidence": 0.85,
            "news_count": 10,
            "summary": "Positive outlook for the stock",
        }
    )
    return client


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
def factor_engine_with_fingpt(mock_market_data_client, mock_fingpt_client, mock_redis_client):
    """Create FactorScoringEngine with FinGPT and Redis clients."""
    return FactorScoringEngine(
        market_data_client=mock_market_data_client,
        fingpt_client=mock_fingpt_client,
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
async def test_calculate_value_low_pe(factor_engine, mock_market_data_client):
    """Test value calculation with low P/E (good value)."""
    from shared.generated import market_data_pb2

    # Mock stock info with low P/E
    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
        pe_ratio=8.0,  # Low P/E = high value score
    )

    value = await factor_engine._calculate_value("AAPL")
    assert value == 100.0  # P/E < 10


@pytest.mark.asyncio
async def test_calculate_value_medium_pe(factor_engine, mock_market_data_client):
    """Test value calculation with medium P/E."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
        pe_ratio=17.0,  # Medium P/E
    )

    value = await factor_engine._calculate_value("AAPL")
    assert value == 60.0  # P/E 15-20


@pytest.mark.asyncio
async def test_calculate_value_high_pe(factor_engine, mock_market_data_client):
    """Test value calculation with high P/E (expensive)."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
        pe_ratio=35.0,  # High P/E = low value score
    )

    value = await factor_engine._calculate_value("AAPL")
    assert value == 10.0  # P/E >= 30


@pytest.mark.asyncio
async def test_calculate_value_negative_pe(factor_engine, mock_market_data_client):
    """Test value calculation with negative P/E (losses)."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="LOSS",
        name="Loss Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=1_000_000_000,
        pe_ratio=-5.0,  # Negative P/E (company has losses)
    )

    value = await factor_engine._calculate_value("LOSS")
    assert value == 50.0  # Neutral for negative P/E


@pytest.mark.asyncio
async def test_calculate_value_missing_pe(factor_engine, mock_market_data_client):
    """Test value calculation when P/E is not available."""
    from shared.generated import market_data_pb2

    # Stock info without pe_ratio field set
    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
        # pe_ratio not set
    )

    value = await factor_engine._calculate_value("AAPL")
    assert value == 50.0  # Neutral when P/E unavailable


@pytest.mark.asyncio
async def test_calculate_value_api_error(factor_engine, mock_market_data_client):
    """Test value calculation when API call fails."""
    mock_market_data_client.get_stock_info.side_effect = Exception("API Error")

    value = await factor_engine._calculate_value("AAPL")
    assert value == 50.0  # Fallback to neutral


@pytest.mark.asyncio
async def test_calculate_quality_large_cap(factor_engine, mock_market_data_client):
    """Test quality calculation for large cap company."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,  # $3T - mega cap
    )

    quality = await factor_engine._calculate_quality("AAPL")
    assert quality == 90.0  # Large cap, capped at 90


@pytest.mark.asyncio
async def test_calculate_quality_mid_cap(factor_engine, mock_market_data_client):
    """Test quality calculation for mid cap company."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="MID",
        name="Mid Cap Inc.",
        sector="Technology",
        industry="Software",
        exchange="NASDAQ",
        currency="USD",
        market_cap=50_000_000_000,  # $50B - mid cap
    )

    quality = await factor_engine._calculate_quality("MID")
    # Mid cap: 50 + ((50B - 10B) / 90B) * 20 = 50 + (40/90)*20 ≈ 58.89
    assert 55.0 <= quality <= 65.0


@pytest.mark.asyncio
async def test_calculate_quality_small_cap(factor_engine, mock_market_data_client):
    """Test quality calculation for small cap company."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="SMALL",
        name="Small Cap Inc.",
        sector="Technology",
        industry="Software",
        exchange="NASDAQ",
        currency="USD",
        market_cap=5_000_000_000,  # $5B - small cap
    )

    quality = await factor_engine._calculate_quality("SMALL")
    # Small cap: 30 + (5B / 10B) * 20 = 30 + 0.5 * 20 = 40
    assert quality == 40.0


@pytest.mark.asyncio
async def test_calculate_quality_invalid_market_cap(factor_engine, mock_market_data_client):
    """Test quality calculation with invalid market cap."""
    from shared.generated import market_data_pb2

    mock_market_data_client.get_stock_info.return_value = market_data_pb2.GetStockInfoResponse(
        symbol="INVALID",
        name="Invalid Inc.",
        sector="Technology",
        industry="Software",
        exchange="NASDAQ",
        currency="USD",
        market_cap=0,  # Invalid
    )

    quality = await factor_engine._calculate_quality("INVALID")
    assert quality == 50.0  # Neutral for invalid


@pytest.mark.asyncio
async def test_calculate_quality_api_error(factor_engine, mock_market_data_client):
    """Test quality calculation when API call fails."""
    mock_market_data_client.get_stock_info.side_effect = Exception("API Error")

    quality = await factor_engine._calculate_quality("AAPL")
    assert quality == 50.0  # Fallback to neutral


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


# FinGPT Sentiment Analysis Tests


@pytest.mark.asyncio
async def test_calculate_sentiment_fingpt_success(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test sentiment calculation using FinGPT with high confidence."""
    # FinGPT returns positive sentiment with high confidence
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": 0.6,  # Bullish
        "confidence": 0.85,  # Above 0.5 threshold
        "news_count": 15,
        "summary": "Strong positive sentiment",
    }

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # Convert 0.6 to 0-100 scale: (0.6 + 1.0) * 50 = 80.0
    assert sentiment == 80.0

    # Should cache the result
    mock_redis_client.setex.assert_called_once()


@pytest.mark.asyncio
async def test_calculate_sentiment_fingpt_bearish(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test bearish sentiment from FinGPT."""
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": -0.5,  # Bearish
        "confidence": 0.9,
        "news_count": 20,
        "summary": "Negative outlook",
    }

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # Convert -0.5 to 0-100 scale: (-0.5 + 1.0) * 50 = 25.0
    assert sentiment == 25.0


@pytest.mark.asyncio
async def test_calculate_sentiment_fingpt_neutral(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test neutral sentiment from FinGPT."""
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": 0.0,  # Neutral
        "confidence": 0.75,
        "news_count": 10,
        "summary": "Mixed sentiment",
    }

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # Convert 0.0 to 0-100 scale: (0.0 + 1.0) * 50 = 50.0
    assert sentiment == 50.0


@pytest.mark.asyncio
async def test_calculate_sentiment_fingpt_low_confidence_fallback(
    factor_engine_with_fingpt,
    mock_fingpt_client,
    mock_redis_client,
    mock_market_data_client,
):
    """Test fallback to momentum when FinGPT confidence is low."""
    # FinGPT returns low confidence
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": 0.8,
        "confidence": 0.3,  # Below 0.5 threshold
        "news_count": 2,
        "summary": "Limited data",
    }

    # Mock OHLCV data for momentum fallback (uptrend)
    mock_ohlcv = [{"close": 100.0 + i * 2, "volume": 1_000_000} for i in range(30)]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # Should use momentum proxy, not FinGPT result
    assert 60.0 <= sentiment <= 80.0  # High momentum range

    # Should NOT cache low confidence result
    mock_redis_client.setex.assert_not_called()


@pytest.mark.asyncio
async def test_calculate_sentiment_fingpt_error_fallback(
    factor_engine_with_fingpt,
    mock_fingpt_client,
    mock_redis_client,
    mock_market_data_client,
):
    """Test fallback to momentum when FinGPT call fails."""
    # FinGPT raises exception
    mock_fingpt_client.analyze_sentiment.side_effect = Exception("API Error")

    # Mock OHLCV data for momentum fallback (neutral)
    mock_ohlcv = [{"close": 150.0, "volume": 1_000_000} for _ in range(30)]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # Should use momentum proxy
    assert 40.0 <= sentiment <= 60.0  # Neutral momentum range


@pytest.mark.asyncio
async def test_calculate_sentiment_uses_cache(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test that cached sentiment is used when available."""
    # Redis returns cached value
    mock_redis_client.get.return_value = 75.0

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # Should use cached value
    assert sentiment == 75.0

    # Should NOT call FinGPT
    mock_fingpt_client.analyze_sentiment.assert_not_called()


@pytest.mark.asyncio
async def test_calculate_sentiment_caches_result(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test that sentiment result is cached in Redis."""
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": 0.4,
        "confidence": 0.8,
        "news_count": 12,
        "summary": "Positive",
    }

    await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # Verify cache was set
    mock_redis_client.setex.assert_called_once()
    call_args = mock_redis_client.setex.call_args

    # Check cache key
    assert call_args[0][0] == "sentiment:AAPL"

    # Check score value (0.4 -> 70.0)
    assert call_args[0][2] == 70.0


@pytest.mark.asyncio
async def test_calculate_sentiment_without_fingpt_client(factor_engine, mock_market_data_client):
    """Test sentiment calculation without FinGPT client (original behavior)."""
    # Create OHLCV data with uptrend
    mock_ohlcv = [{"close": 100.0 + i * 2, "volume": 1_000_000} for i in range(30)]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine._calculate_sentiment("AAPL")

    # Should use momentum proxy (high momentum = bullish sentiment)
    assert 60.0 <= sentiment <= 80.0


@pytest.mark.asyncio
async def test_calculate_sentiment_clips_to_bounds(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test that sentiment score is clipped to 0-100 range."""
    # FinGPT returns maximum bullish sentiment
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": 1.0,  # Maximum bullish
        "confidence": 0.95,
        "news_count": 30,
        "summary": "Extremely positive",
    }

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # (1.0 + 1.0) * 50 = 100.0, should be clipped
    assert sentiment == 100.0


@pytest.mark.asyncio
async def test_calculate_sentiment_clips_minimum(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test that minimum bearish sentiment is clipped."""
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": -1.0,  # Maximum bearish
        "confidence": 0.95,
        "news_count": 25,
        "summary": "Extremely negative",
    }

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # (-1.0 + 1.0) * 50 = 0.0
    assert sentiment == 0.0


@pytest.mark.asyncio
async def test_cache_sentiment_handles_redis_error(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test that cache errors don't break sentiment calculation."""
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": 0.5,
        "confidence": 0.8,
        "news_count": 10,
        "summary": "Positive",
    }
    mock_redis_client.setex.side_effect = Exception("Redis connection error")

    # Should not raise, just log warning
    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    assert sentiment == 75.0  # (0.5 + 1.0) * 50 = 75.0


@pytest.mark.asyncio
async def test_get_cached_sentiment_handles_redis_error(
    factor_engine_with_fingpt, mock_fingpt_client, mock_redis_client
):
    """Test that cache retrieval errors fall back to FinGPT."""
    mock_redis_client.get.side_effect = Exception("Redis connection error")
    mock_fingpt_client.analyze_sentiment.return_value = {
        "sentiment": 0.3,
        "confidence": 0.75,
        "news_count": 8,
        "summary": "Slightly positive",
    }

    sentiment = await factor_engine_with_fingpt._calculate_sentiment("AAPL")

    # Should fall back to FinGPT
    assert sentiment == 65.0  # (0.3 + 1.0) * 50 = 65.0
    mock_fingpt_client.analyze_sentiment.assert_called_once()


@pytest.mark.asyncio
async def test_calculate_sentiment_from_momentum_directly(factor_engine, mock_market_data_client):
    """Test the _calculate_sentiment_from_momentum method directly."""
    # Create OHLCV data with downtrend
    mock_ohlcv = [{"close": 200.0 - i * 3, "volume": 1_000_000} for i in range(30)]
    mock_market_data_client.get_ohlcv.return_value = mock_ohlcv

    sentiment = await factor_engine._calculate_sentiment_from_momentum("AAPL")

    # Downtrend should give low sentiment (20-40)
    assert 20.0 <= sentiment <= 40.0
