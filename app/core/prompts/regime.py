"""Prompt formatting for market regime classification.

Pure string formatting — no I/O, no infrastructure dependencies.
YAML loading is handled by the service layer.

Source: services/market-regime/src/prompts/formatter.py
"""

from typing import Any

# Default values for missing indicators
REGIME_DEFAULTS: dict[str, str] = {
    "vix": "N/A",
    "sp500_1m_change": "N/A",
    "high_low_ratio": "N/A",
    "fed_funds_rate": "N/A",
    "yield_curve_10y_2y": "N/A",
    "cpi_yoy": "N/A",
    "unemployment_rate": "N/A",
    "credit_spread": "N/A",
}

REGIME_SYSTEM_PROMPT = (
    "You are a financial market analyst specializing in market regime classification. "
    "Analyze market conditions and classify the current market regime based on provided data. "
    "Always respond with valid JSON matching the specified schema."
)

REGIME_TEMPLATE = """Analyze the current market conditions and classify the market regime.

## Market Data
- VIX (Volatility Index): {vix}
- S&P 500 Change (1 Month): {sp500_1m_change}%
- 52-Week High/Low Ratio: {high_low_ratio}

## Macro Economic Indicators
- Federal Funds Rate: {fed_funds_rate}%
- 10Y-2Y Treasury Yield Spread: {yield_curve_10y_2y} bps
- CPI Year-over-Year: {cpi_yoy}%
- Unemployment Rate: {unemployment_rate}%
- Credit Spread (High Yield - Investment Grade): {credit_spread} bps

## Classification Guidelines
Based on the data above, classify into ONE of these regimes:
- crisis: High volatility, risk-off environment. VIX > 30, major market drawdowns, flight to safety.
- bear: Declining market with moderate volatility. Negative momentum, risk reduction recommended.
- bull: Rising market with low-moderate volatility. Positive momentum, risk-on environment.
- sideways: Range-bound market with no clear direction. Mixed signals, neutral positioning.
- recovery: Transition from crisis/bear to bull. Improving conditions, gradual risk increase.

Provide your analysis as JSON with regime, confidence (0.0-1.0), reasoning, and key_indicators."""


def format_regime_prompt(
    market_data: dict[str, Any],
    macro_indicators: dict[str, Any],
) -> str:
    """Format the regime classification prompt with actual market data.

    Args:
        market_data: Market data dictionary (vix, sp500_1m_change, etc.).
        macro_indicators: Macro economic indicators.

    Returns:
        Formatted prompt string ready for LLM.
    """
    data = {**REGIME_DEFAULTS}
    data.update({k: v for k, v in market_data.items() if v is not None})
    data.update({k: v for k, v in macro_indicators.items() if v is not None})

    return REGIME_TEMPLATE.format(**data)
