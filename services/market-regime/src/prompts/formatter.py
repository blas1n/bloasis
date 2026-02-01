"""
Prompt formatting utilities for market regime classification.

Provides functions to format prompts with market data and retrieve
schema/parameter configurations from YAML templates.
"""

from typing import Any

from .loader import load_prompt


def get_classification_prompt() -> dict[str, Any]:
    """
    Get the regime classification prompt configuration.

    Returns:
        Full classification prompt configuration from YAML.
    """
    return load_prompt("regime_classification")


def format_classification_prompt(
    market_data: dict[str, Any],
    macro_indicators: dict[str, Any],
) -> str:
    """
    Format the classification prompt with actual data.

    Args:
        market_data: Market data dictionary (vix, sp500_1m_change, etc.).
        macro_indicators: Macro economic indicators (fed_funds_rate, etc.).

    Returns:
        Formatted prompt string ready for LLM.
    """
    config = get_classification_prompt()
    template = config["classification"]["template"]
    defaults = config["classification"]["defaults"]

    # Merge data with defaults
    data = {**defaults}
    data.update({k: v for k, v in market_data.items() if v is not None})
    data.update({k: v for k, v in macro_indicators.items() if v is not None})

    return template.format(**data)


def get_response_schema() -> dict[str, Any]:
    """
    Get the JSON schema for structured output.

    Returns:
        JSON schema dictionary for validating LLM responses.
    """
    config = get_classification_prompt()
    return config["classification"]["response_schema"]


def get_model_parameters() -> dict[str, Any]:
    """
    Get model generation parameters.

    Returns:
        Dictionary of model parameters (max_new_tokens, temperature, etc.).
    """
    config = get_classification_prompt()
    return config.get("parameters", {})
