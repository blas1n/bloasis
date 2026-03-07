"""ATR-based trading signal generation — pure functions.

Converts technical analysis signals into actionable trading signals with:
- ATR-based stop-loss and take-profit levels
- Volatility-adjusted position sizing
- 3-tier profit-taking with trailing stop

Source: services/strategy/src/agents/signal_generator.py
"""

import math
from decimal import Decimal
from typing import Any

from .models import ProfitTier, RiskLevel, SignalAction, TradingSignal
from .technical_indicators import calculate_indicators

# Risk multiplier by market risk level — scales ATR distances
RISK_MULTIPLIERS: dict[str, Decimal] = {
    RiskLevel.EXTREME: Decimal("0.5"),
    RiskLevel.HIGH: Decimal("0.75"),
    RiskLevel.MEDIUM: Decimal("1.0"),
    RiskLevel.LOW: Decimal("1.25"),
}

# Target annualized volatility by risk profile (for position sizing)
TARGET_VOLATILITY: dict[str, float] = {
    "conservative": 0.10,
    "moderate": 0.15,
    "aggressive": 0.25,
}

# Max position sizes by risk profile (hard cap)
MAX_POSITION_SIZE: dict[str, Decimal] = {
    "conservative": Decimal("0.05"),
    "moderate": Decimal("0.10"),
    "aggressive": Decimal("0.15"),
}


def generate_signal(
    symbol: str,
    direction: str,
    strength: float,
    entry_price: Decimal,
    risk_level: str,
    risk_profile: str,
    ohlcv_bars: list[dict[str, Any]] | None = None,
    rationale: str = "",
    risk_approved: bool = True,
    position_adjustment: float = 1.0,
) -> TradingSignal:
    """Generate a single trading signal with ATR-based levels.

    Args:
        symbol: Stock ticker.
        direction: Signal direction ("long", "short", "neutral").
        strength: Signal strength (0-1).
        entry_price: Current/recommended entry price.
        risk_level: Market risk level.
        risk_profile: User risk profile.
        ohlcv_bars: OHLCV data for ATR calculation.
        rationale: Trading rationale text.
        risk_approved: Whether risk manager approved.
        position_adjustment: Multiplier from risk assessment.

    Returns:
        TradingSignal with computed levels.
    """
    action = _direction_to_action(direction)
    atr = _get_atr(symbol, ohlcv_bars)

    # Position sizing
    base_size = _calculate_position_size(strength, risk_profile, atr, float(entry_price))
    final_size = (base_size * Decimal(str(position_adjustment))).quantize(Decimal("0.0001"))

    # ATR-based levels
    stop_loss, take_profit = _calculate_levels(
        entry_price,
        direction,
        risk_level,
        atr,
    )

    # Multi-tier profit taking
    profit_tiers, trailing_stop_pct = _calculate_profit_tiers(
        entry_price,
        direction,
        risk_level,
        atr,
    )

    return TradingSignal(
        symbol=symbol,
        action=action,
        confidence=strength,
        size_recommendation=final_size,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rationale=rationale,
        risk_approved=risk_approved,
        profit_tiers=profit_tiers,
        trailing_stop_pct=trailing_stop_pct,
    )


def _get_atr(symbol: str, bars: list[dict[str, Any]] | None) -> float:
    """Get ATR from OHLCV bars."""
    if not bars or len(bars) < 26:
        return 0.0
    indicators = calculate_indicators(symbol, bars)
    return indicators.atr_14 if indicators else 0.0


def _calculate_position_size(
    strength: float,
    risk_profile: str,
    atr: float,
    entry_price: float,
) -> Decimal:
    """Calculate volatility-adjusted position size.

    Uses inverse-volatility weighting capped at max_size per risk profile.
    """
    profile = risk_profile.lower()
    max_size = MAX_POSITION_SIZE.get(profile, Decimal("0.10"))
    target_vol = TARGET_VOLATILITY.get(profile, 0.15)

    base = Decimal(str(strength)) * max_size

    if atr > 0 and entry_price > 0:
        atr_d = Decimal(str(atr))
        entry_d = Decimal(str(entry_price))
        daily_vol = atr_d / entry_d
        annual_vol = daily_vol * Decimal(str(math.sqrt(252)))

        if annual_vol > 0:
            vol_ratio = Decimal(str(target_vol)) / annual_vol
            vol_ratio = max(Decimal("0.3"), min(Decimal("2.0"), vol_ratio))
            base = base * vol_ratio

    return min(base, max_size).quantize(Decimal("0.0001"))


def _calculate_levels(
    entry: Decimal,
    direction: str,
    risk_level: str,
    atr: float,
) -> tuple[Decimal, Decimal]:
    """Calculate ATR-based stop-loss and take-profit.

    SL = entry +/- (2 * ATR * risk_mult)
    TP = entry +/- (3 * ATR * risk_mult)
    """
    risk_mult = RISK_MULTIPLIERS.get(risk_level, Decimal("1.0"))

    if atr > 0:
        atr_d = Decimal(str(atr))
        sl_dist = Decimal("2") * atr_d * risk_mult
        tp_dist = Decimal("3") * atr_d * risk_mult

        if direction == "long":
            return entry - sl_dist, entry + tp_dist
        else:
            return entry + sl_dist, entry - tp_dist
    else:
        sl_pct, tp_pct = _fallback_pct(direction, risk_level)
        return entry * sl_pct, entry * tp_pct


def _calculate_profit_tiers(
    entry: Decimal,
    direction: str,
    risk_level: str,
    atr: float,
) -> tuple[list[ProfitTier], Decimal]:
    """Calculate 3-tier profit-taking levels and trailing stop.

    Tier 1 (33%): 1.5 * ATR
    Tier 2 (33%): 3.0 * ATR
    Tier 3 (34%): trailing stop
    """
    risk_mult = RISK_MULTIPLIERS.get(risk_level, Decimal("1.0"))

    if atr > 0:
        atr_d = Decimal(str(atr))
        t1_dist = Decimal("1.5") * atr_d * risk_mult
        t2_dist = Decimal("3.0") * atr_d * risk_mult

        if direction == "long":
            t1_level = entry + t1_dist
            t2_level = entry + t2_dist
        else:
            t1_level = entry - t1_dist
            t2_level = entry - t2_dist

        trailing_pct = (
            (Decimal("2") * atr_d * risk_mult / entry * 100) if entry > 0 else Decimal("2.0")
        ).quantize(Decimal("0.01"))
    else:
        if risk_level == RiskLevel.EXTREME:
            t1_pct, t2_pct, trailing_pct = Decimal("0.01"), Decimal("0.02"), Decimal("1.0")
        elif risk_level == RiskLevel.HIGH:
            t1_pct, t2_pct, trailing_pct = Decimal("0.015"), Decimal("0.03"), Decimal("1.5")
        else:
            t1_pct, t2_pct, trailing_pct = Decimal("0.025"), Decimal("0.05"), Decimal("2.0")

        if direction == "long":
            t1_level = entry * (Decimal("1") + t1_pct)
            t2_level = entry * (Decimal("1") + t2_pct)
        else:
            t1_level = entry * (Decimal("1") - t1_pct)
            t2_level = entry * (Decimal("1") - t2_pct)

    tiers = [
        ProfitTier(level=t1_level, size_pct=Decimal("0.33")),
        ProfitTier(level=t2_level, size_pct=Decimal("0.33")),
        ProfitTier(level=Decimal("0"), size_pct=Decimal("0.34")),  # Trailing stop tier
    ]

    return tiers, trailing_pct


def _fallback_pct(direction: str, risk_level: str) -> tuple[Decimal, Decimal]:
    """Get fallback SL/TP percentages when ATR is unavailable."""
    if risk_level == RiskLevel.EXTREME:
        sl, tp = Decimal("0.005"), Decimal("0.02")
    elif risk_level == RiskLevel.HIGH:
        sl, tp = Decimal("0.01"), Decimal("0.03")
    else:
        sl, tp = Decimal("0.02"), Decimal("0.05")

    if direction == "long":
        return (Decimal("1") - sl, Decimal("1") + tp)
    else:
        return (Decimal("1") + sl, Decimal("1") - tp)


def _direction_to_action(direction: str) -> SignalAction:
    """Convert signal direction to trading action."""
    return {
        "long": SignalAction.BUY,
        "short": SignalAction.SELL,
    }.get(direction, SignalAction.HOLD)
