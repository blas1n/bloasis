"""Market regime classification — pure functions.

Validates and normalizes LLM classification responses.
Calculates risk level from regime + VIX.

Source: services/market-regime/src/models.py:185-226
"""

from .models import RegimeType, RiskLevel

VALID_REGIMES = {r.value for r in RegimeType}


def parse_regime_response(data: dict) -> dict:
    """Validate and normalize Claude's regime classification response.

    Args:
        data: Parsed JSON from Claude API.

    Returns:
        Validated dict with regime, confidence, reasoning, indicators.
    """
    try:
        regime = data.get("regime", "sideways")
        if regime not in VALID_REGIMES:
            regime = "sideways"

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        return {
            "regime": regime,
            "confidence": confidence,
            "reasoning": data.get("reasoning", "Unable to determine"),
            "indicators": data.get("key_indicators", []),
        }

    except (KeyError, TypeError, ValueError):
        return {
            "regime": "sideways",
            "confidence": 0.5,
            "reasoning": "Parse error",
            "indicators": [],
        }


def calculate_risk_level(regime: str, vix: float) -> RiskLevel:
    """Calculate risk level based on regime and VIX.

    Args:
        regime: Market regime classification.
        vix: Current VIX value.

    Returns:
        Risk level ("low", "medium", "high", "extreme").
    """
    if regime == RegimeType.CRISIS or vix >= 40:
        return RiskLevel.EXTREME
    elif regime == RegimeType.BEAR or vix >= 30:
        return RiskLevel.HIGH
    elif vix > 20:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.LOW
