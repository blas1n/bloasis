"""Prompt formatting for sector/theme classification.

Source: services/strategy/src/prompts/formatter.py (format_macro_prompt)
"""

SECTOR_SYSTEM_PROMPT = (
    "You are a macro strategist specializing in market regime"
    " analysis for algorithmic trading. Your task is to analyze"
    " the macro economic environment and provide sector allocation"
    " recommendations."
    " Always respond with valid JSON matching the specified schema."
)

SECTOR_TEMPLATE = """Analyze the current market environment for sector allocation.

**Current Regime**: {regime}
**Sectors**: {sectors}
**Candidate Symbols**: {symbols}

Provide:
1. Overall market risk level (low/medium/high/extreme)
2. Sector-specific outlook (score 0-100 for each sector)
3. Key macro indicators affecting these sectors
4. Rationale

Output JSON format:
{{
  "risk_level": "medium",
  "sector_outlook": {{"Technology": 75, "Healthcare": 60}},
  "macro_indicators": {{"inflation": "rising", "rates": "stable", "gdp_growth": "moderate"}},
  "rationale": "Market shows moderate risk..."
}}"""


def format_sector_prompt(
    symbols: list[str],
    regime: str,
    sectors: list[str],
) -> str:
    """Format the sector analysis prompt.

    Args:
        symbols: List of stock symbols.
        regime: Current market regime.
        sectors: List of sectors to analyze.

    Returns:
        Formatted prompt string.
    """
    return SECTOR_TEMPLATE.format(
        symbols=", ".join(symbols) if symbols else "None",
        regime=regime or "unknown",
        sectors=", ".join(sectors) if sectors else "All GICS sectors",
    )
