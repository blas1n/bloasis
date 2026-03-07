"""6-factor scoring engine — pure calculation functions.

No infrastructure dependencies. Takes raw data, returns scores.

Factors:
- Momentum: Price trend vs MA20
- Value: P/E bell-curve + Profit Margin + Current Ratio
- Quality: ROE + D/E + Profit Margin + Current Ratio + Market Cap
- Volatility: Annualized std dev (inverse scoring)
- Liquidity: Average daily volume
- Sentiment: Momentum proxy (or cached value)

Source: services/strategy/src/factor_scoring.py
"""

import math
import statistics
from decimal import Decimal

from .models import FactorScores, RiskProfile

# Factor weights by risk profile
FACTOR_WEIGHTS: dict[str, dict[str, float]] = {
    RiskProfile.CONSERVATIVE: {
        "momentum": 0.10,
        "value": 0.25,
        "quality": 0.30,
        "volatility": 0.20,
        "liquidity": 0.10,
        "sentiment": 0.05,
    },
    RiskProfile.MODERATE: {
        "momentum": 0.20,
        "value": 0.20,
        "quality": 0.20,
        "volatility": 0.15,
        "liquidity": 0.10,
        "sentiment": 0.15,
    },
    RiskProfile.AGGRESSIVE: {
        "momentum": 0.30,
        "value": 0.10,
        "quality": 0.15,
        "volatility": 0.05,
        "liquidity": 0.10,
        "sentiment": 0.30,
    },
}

# Regime-adaptive multipliers
REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "crisis": {
        "momentum": 0.3,
        "value": 1.5,
        "quality": 1.8,
        "volatility": 2.0,
        "liquidity": 1.0,
        "sentiment": 0.2,
    },
    "bear": {
        "momentum": 0.6,
        "value": 1.3,
        "quality": 1.4,
        "volatility": 1.5,
        "liquidity": 1.0,
        "sentiment": 0.5,
    },
    "sideways": {
        "momentum": 0.8,
        "value": 1.2,
        "quality": 1.0,
        "volatility": 1.0,
        "liquidity": 1.0,
        "sentiment": 0.8,
    },
    "recovery": {
        "momentum": 1.5,
        "value": 1.2,
        "quality": 0.8,
        "volatility": 0.7,
        "liquidity": 1.0,
        "sentiment": 1.3,
    },
    "bull": {
        "momentum": 1.2,
        "value": 0.8,
        "quality": 0.9,
        "volatility": 0.7,
        "liquidity": 1.0,
        "sentiment": 1.2,
    },
}


def calculate_final_score(
    factor_scores: FactorScores,
    risk_profile: str,
    regime: str = "bull",
) -> Decimal:
    """Calculate weighted final score based on risk profile and market regime.

    Applies regime-adaptive multipliers to base weights, then normalizes.

    Args:
        factor_scores: Individual factor scores.
        risk_profile: User's risk profile.
        regime: Current market regime.

    Returns:
        Final weighted score (0-100) as Decimal.
    """
    profile_key = risk_profile.lower()
    base_weights = FACTOR_WEIGHTS.get(profile_key, FACTOR_WEIGHTS[RiskProfile.MODERATE])
    regime_mults = REGIME_MULTIPLIERS.get(regime, {})

    # Apply regime multipliers
    adjusted: dict[str, float] = {}
    for factor, base_w in base_weights.items():
        mult = regime_mults.get(factor, 1.0)
        adjusted[factor] = base_w * mult

    # Normalize so weights sum to 1.0
    total = sum(adjusted.values())
    if total > 0:
        weights = {k: v / total for k, v in adjusted.items()}
    else:
        weights = base_weights

    scores = {
        "momentum": factor_scores.momentum,
        "value": factor_scores.value,
        "quality": factor_scores.quality,
        "volatility": factor_scores.volatility,
        "liquidity": factor_scores.liquidity,
        "sentiment": factor_scores.sentiment,
    }

    score = sum(Decimal(str(scores[k])) * Decimal(str(weights[k])) for k in weights)

    return score.quantize(Decimal("0.01"))


def calculate_momentum(bars: list[dict]) -> float:
    """Calculate momentum score (0-100).

    Based on price position relative to 20-day MA.
    +10% above MA20 = 100, -10% below = 0.

    Args:
        bars: OHLCV data bars (dicts with 'close' key).

    Returns:
        Momentum score (0-100).
    """
    if len(bars) < 20:
        return 50.0

    recent_close = bars[-1]["close"]
    ma20 = sum(bar["close"] for bar in bars[-20:]) / 20

    if ma20 == 0:
        return 50.0

    momentum_pct = ((recent_close - ma20) / ma20) * 100
    return max(0.0, min(100.0, 50.0 + (momentum_pct * 5)))


def calculate_volatility(bars: list[dict]) -> float:
    """Calculate volatility score (0-100, inverse).

    Lower volatility = higher score.
    Based on annualized standard deviation of daily returns.

    Args:
        bars: OHLCV data bars (dicts with 'close' key).

    Returns:
        Volatility score (0-100).
    """
    if len(bars) < 20:
        return 50.0

    returns = [
        (bars[i]["close"] - bars[i - 1]["close"]) / bars[i - 1]["close"]
        for i in range(1, len(bars))
        if bars[i - 1]["close"] != 0
    ]

    if len(returns) < 2:
        return 50.0

    std_dev = statistics.stdev(returns) * (252**0.5)
    return max(0.0, 100.0 - (std_dev * 500))


def calculate_liquidity(bars: list[dict]) -> float:
    """Calculate liquidity score (0-100).

    Based on 20-day average volume. 1M+ volume = 100.

    Args:
        bars: OHLCV data bars (dicts with 'volume' key).

    Returns:
        Liquidity score (0-100).
    """
    if len(bars) < 20:
        return 50.0

    avg_volume = sum(bar["volume"] for bar in bars[-20:]) / 20
    return min(100.0, (avg_volume / 1_000_000) * 100)


def calculate_value(
    pe_ratio: float | None = None,
    profit_margin: float | None = None,
    current_ratio: float | None = None,
) -> float:
    """Calculate value score (0-100).

    P/E ratio (40%): Bell-curve peaking at PE=12.
    Profit Margin (30%): Higher = better.
    Current Ratio (30%): Peak at 1.5-2.0.

    Args:
        pe_ratio: Price-to-earnings ratio (None if unavailable).
        profit_margin: Profit margin as decimal (e.g. 0.15 = 15%).
        current_ratio: Current ratio (None if unavailable).

    Returns:
        Value score (0-100).
    """
    # P/E score (40%)
    if pe_ratio is not None:
        if pe_ratio <= 0:
            pe_score = 30.0
        else:
            pe_score = 100.0 * math.exp(-(((pe_ratio - 12) / 10) ** 2))
    else:
        pe_score = 50.0

    # Profit Margin score (30%)
    if profit_margin is not None:
        if profit_margin < 0:
            pm_score = max(0.0, 20.0 + profit_margin * 100)
        else:
            pm_score = min(100.0, profit_margin * 500)
    else:
        pm_score = 50.0

    # Current Ratio score (30%)
    if current_ratio is not None:
        if current_ratio <= 0:
            cr_score = 0.0
        elif current_ratio < 1.0:
            cr_score = current_ratio * 50.0
        elif current_ratio <= 2.0:
            cr_score = 50.0 + (current_ratio - 1.0) * 50.0
        else:
            cr_score = max(40.0, 100.0 - (current_ratio - 2.0) * 15.0)
    else:
        cr_score = 50.0

    return pe_score * 0.4 + pm_score * 0.3 + cr_score * 0.3


def calculate_quality(
    return_on_equity: float | None = None,
    debt_to_equity: float | None = None,
    profit_margin: float | None = None,
    current_ratio: float | None = None,
    market_cap: float = 0.0,
) -> float:
    """Calculate quality score (0-100).

    ROE (25%) + D/E inverse (20%) + Profit Margin (25%)
    + Current Ratio (15%) + Market Cap log (15%).

    Args:
        return_on_equity: ROE as decimal (e.g. 0.15 = 15%).
        debt_to_equity: Debt-to-equity ratio.
        profit_margin: Profit margin as decimal.
        current_ratio: Current ratio.
        market_cap: Market capitalization in USD.

    Returns:
        Quality score (0-100).
    """
    # ROE (25%)
    if return_on_equity is not None:
        if return_on_equity < 0:
            roe_score = max(0.0, 20.0 + return_on_equity * 100)
        else:
            roe_score = min(100.0, return_on_equity * 400)
    else:
        roe_score = 50.0

    # D/E (20%) — lower is better
    if debt_to_equity is not None:
        de_score = max(0.0, 100.0 - debt_to_equity * 50)
    else:
        de_score = 50.0

    # Profit Margin (25%)
    if profit_margin is not None:
        if profit_margin < 0:
            pm_score = max(0.0, 20.0 + profit_margin * 100)
        else:
            pm_score = min(100.0, profit_margin * 400)
    else:
        pm_score = 50.0

    # Current Ratio (15%)
    if current_ratio is not None:
        if current_ratio <= 0:
            cr_score = 0.0
        elif current_ratio < 1.0:
            cr_score = current_ratio * 50.0
        elif current_ratio <= 2.0:
            cr_score = 50.0 + (current_ratio - 1.0) * 50.0
        else:
            cr_score = max(40.0, 100.0 - (current_ratio - 2.0) * 15.0)
    else:
        cr_score = 50.0

    # Market Cap (15%)
    if market_cap <= 0:
        cap_score = 50.0
    elif market_cap >= 100_000_000_000:
        cap_score = min(90.0, 70.0 + (market_cap / 1_000_000_000_000) * 10)
    elif market_cap >= 10_000_000_000:
        ratio = (market_cap - 10_000_000_000) / 90_000_000_000
        cap_score = 50.0 + ratio * 20
    else:
        ratio = market_cap / 10_000_000_000
        cap_score = 30.0 + ratio * 20

    return roe_score * 0.25 + de_score * 0.20 + pm_score * 0.25 + cr_score * 0.15 + cap_score * 0.15


def calculate_sentiment_from_momentum(momentum_score: float) -> float:
    """Calculate sentiment score using momentum as proxy.

    High momentum (>70) → bullish sentiment (60-80).
    Low momentum (<30) → bearish sentiment (20-40).
    Neutral → 40-60.

    Args:
        momentum_score: Momentum score (0-100).

    Returns:
        Sentiment score (0-100).
    """
    if momentum_score > 70:
        return 60.0 + (momentum_score - 70) * (20.0 / 30.0)
    elif momentum_score < 30:
        return 20.0 + momentum_score * (20.0 / 30.0)
    else:
        return 40.0 + (momentum_score - 30) * (20.0 / 40.0)
