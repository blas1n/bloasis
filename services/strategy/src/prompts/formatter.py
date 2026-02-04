"""
Prompt formatting utilities for Strategy service agents.

Provides functions to format prompts with market data and retrieve
schema/parameter configurations from YAML templates.
"""

from pathlib import Path
from typing import Any

from shared.prompts import PromptLoader

# Create a loader for this service's prompts directory
_loader = PromptLoader(Path(__file__).parent)


def load_prompt(name: str) -> dict[str, Any]:
    """Load a prompt configuration from YAML."""
    return _loader.load(name)


def format_macro_prompt(
    symbols: list[str],
    regime: str,
    sectors: list[str],
) -> tuple[str, str]:
    """
    Format the macro strategist prompt with market data.

    Args:
        symbols: List of stock symbols
        regime: Current market regime
        sectors: List of sectors

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    config = load_prompt("macro_strategist")
    system_prompt = config.get("system_prompt", "")
    user_template = config.get("user_prompt_template", "")
    defaults = config.get("default_values", {})

    # Use provided values or defaults
    symbols_value = symbols if symbols else defaults.get("symbols", [])
    regime_value = regime if regime else defaults.get("regime", "unknown")
    sectors_value = sectors if sectors else defaults.get("sectors", [])

    # Format user prompt
    user_prompt = user_template.format(
        symbols=", ".join(symbols_value),
        regime=regime_value,
        sectors=", ".join(sectors_value),
    )

    return system_prompt.strip(), user_prompt.strip()


def format_technical_prompt(
    stock_data: list[dict],
    ohlcv_summary: str,
    market_context: dict,
) -> tuple[str, str]:
    """
    Format the technical analyst prompt with stock and market data.

    Args:
        stock_data: Stock pick data with factor scores
        ohlcv_summary: Formatted OHLCV data summary
        market_context: Current market context

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    import json

    config = load_prompt("technical_analyst")
    system_prompt = config.get("system_prompt", "")
    user_template = config.get("user_prompt_template", "")

    # Format user prompt
    user_prompt = user_template.format(
        stock_data=json.dumps(stock_data, indent=2),
        regime=market_context.get("regime", "unknown"),
        risk_level=market_context.get("risk_level", "medium"),
        sector_outlook=json.dumps(market_context.get("sector_outlook", {}), indent=2),
        ohlcv_summary=ohlcv_summary,
    )

    return system_prompt.strip(), user_prompt.strip()


def format_risk_prompt(
    signals: list[dict],
    market_context: dict,
    user_preferences: dict,
) -> tuple[str, str]:
    """
    Format the risk manager prompt with signals and context.

    Args:
        signals: Proposed trading signals
        market_context: Current market context
        user_preferences: User risk preferences

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    import json

    config = load_prompt("risk_manager")
    system_prompt = config.get("system_prompt", "")
    user_template = config.get("user_prompt_template", "")
    defaults = config.get("default_values", {})

    # Extract user preferences with defaults
    risk_profile = user_preferences.get("risk_profile", defaults.get("risk_profile", "MODERATE"))
    max_single_position = user_preferences.get(
        "max_single_position", defaults.get("max_single_position", 0.10)
    )
    excluded_sectors = user_preferences.get(
        "excluded_sectors", defaults.get("excluded_sectors", [])
    )

    # Format user prompt
    user_prompt = user_template.format(
        risk_profile=risk_profile,
        max_single_position=max_single_position * 100,
        excluded_sectors=", ".join(excluded_sectors) if excluded_sectors else "None",
        regime=market_context.get("regime", "unknown"),
        risk_level=market_context.get("risk_level", "medium"),
        signals=json.dumps(signals, indent=2),
    )

    return system_prompt.strip(), user_prompt.strip()


def get_macro_response_schema() -> dict[str, Any]:
    """
    Get the JSON schema for macro strategist structured output.

    Returns:
        JSON schema dictionary for validating LLM responses.
    """
    config = load_prompt("macro_strategist")
    return config.get("response_schema", {})


def get_technical_response_schema() -> dict[str, Any]:
    """
    Get the JSON schema for technical analyst structured output.

    Returns:
        JSON schema dictionary for validating LLM responses.
    """
    config = load_prompt("technical_analyst")
    return config.get("response_schema", {})


def get_risk_response_schema() -> dict[str, Any]:
    """
    Get the JSON schema for risk manager structured output.

    Returns:
        JSON schema dictionary for validating LLM responses.
    """
    config = load_prompt("risk_manager")
    return config.get("response_schema", {})


def get_macro_model_parameters() -> dict[str, Any]:
    """
    Get model generation parameters for macro strategist.

    Returns:
        Dictionary of model parameters (max_new_tokens, temperature, etc.).
    """
    config = load_prompt("macro_strategist")
    return config.get("model_parameters", {})


def get_technical_model_parameters() -> dict[str, Any]:
    """
    Get model generation parameters for technical analyst.

    Returns:
        Dictionary of model parameters (max_new_tokens, temperature, etc.).
    """
    config = load_prompt("technical_analyst")
    return config.get("model_parameters", {})


def get_risk_model_parameters() -> dict[str, Any]:
    """
    Get model generation parameters for risk manager.

    Returns:
        Dictionary of model parameters (max_new_tokens, temperature, etc.).
    """
    config = load_prompt("risk_manager")
    return config.get("model_parameters", {})


def format_regime_risk_prompt(
    regime: str,
    indicators: dict,
) -> tuple[str, str]:
    """
    Format the regime risk assessment prompt.

    Args:
        regime: Current market regime
        indicators: Macro economic indicators

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    import json

    config = load_prompt("macro_strategist")
    regime_risk_config = config.get("regime_risk", {})
    system_prompt = regime_risk_config.get("system_prompt", "")
    user_template = regime_risk_config.get("user_prompt_template", "")

    # Format user prompt
    user_prompt = user_template.format(
        regime=regime,
        indicators=json.dumps(indicators, indent=2),
    )

    return system_prompt.strip(), user_prompt.strip()


def get_regime_risk_model_parameters() -> dict[str, Any]:
    """
    Get model generation parameters for regime risk assessment.

    Returns:
        Dictionary of model parameters.
    """
    config = load_prompt("macro_strategist")
    regime_risk_config = config.get("regime_risk", {})
    return regime_risk_config.get("model_parameters", {})
