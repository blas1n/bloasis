"""Prompt formatting for unified technical + risk analysis.

In the monolith, we merge Technical Analyst (Layer 2) and Risk Manager (Layer 3)
into a single Claude call. This module formats the combined prompt.

Source:
- services/strategy/src/prompts/formatter.py (format_technical_prompt, format_risk_prompt)
- services/strategy/src/prompts/technical_analyst.yaml
- services/strategy/src/prompts/risk_manager.yaml
"""

import json
from typing import Any

ANALYSIS_SYSTEM_PROMPT = (
    "You are an expert financial analyst combining technical analysis"
    " and risk assessment. Analyze stocks using technical indicators,"
    " price patterns, and market context. Provide actionable trading"
    " signals with risk-adjusted recommendations."
    " Always respond with valid JSON matching the specified schema."
)

ANALYSIS_TEMPLATE = """Analyze the following stocks for trading opportunities.

**Stock Picks**:
{stock_data}

**Market Context**:
- Regime: {regime}
- Risk Level: {risk_level}
- Sector Outlook: {sector_outlook}

**Technical Data (OHLCV Summary)**:
{ohlcv_summary}

**User Risk Profile**: {risk_profile}
**Max Single Position**: {max_single_position}%
**Excluded Sectors**: {excluded_sectors}

For each stock, provide:
1. Trading direction (long/short/neutral)
2. Signal strength (0-1)
3. Entry price recommendation
4. Key technical indicators (RSI, MACD, trend)
5. Risk assessment for this position
6. Rationale (2-3 sentences)

Output JSON array:
[
  {{
    "symbol": "AAPL",
    "direction": "long",
    "strength": 0.75,
    "entry_price": 150.25,
    "indicators": {{"rsi": 65, "macd": "bullish", "trend": "up"}},
    "risk_note": "Acceptable risk within concentration limits",
    "rationale": "Strong momentum with RSI in healthy range. MACD crossover confirms uptrend."
  }}
]"""


def format_analysis_prompt(
    stock_data: list[dict],
    ohlcv_summary: str,
    market_context: dict[str, Any],
    user_preferences: dict[str, Any],
) -> str:
    """Format the combined analysis prompt.

    Args:
        stock_data: Stock pick data with factor scores.
        ohlcv_summary: Formatted OHLCV data summary.
        market_context: Current market context (regime, risk_level, sector_outlook).
        user_preferences: User risk preferences.

    Returns:
        Formatted prompt string.
    """
    risk_profile = user_preferences.get("risk_profile", "moderate")
    max_single_position = user_preferences.get("max_single_position", 0.10) * 100
    excluded = user_preferences.get("excluded_sectors", [])
    excluded_str = ", ".join(excluded) if excluded else "None"

    return ANALYSIS_TEMPLATE.format(
        stock_data=json.dumps(stock_data, indent=2),
        regime=market_context.get("regime", "unknown"),
        risk_level=market_context.get("risk_level", "medium"),
        sector_outlook=json.dumps(market_context.get("sector_outlook", {}), indent=2),
        ohlcv_summary=ohlcv_summary,
        risk_profile=risk_profile,
        max_single_position=max_single_position,
        excluded_sectors=excluded_str,
    )
