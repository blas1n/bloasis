"""
Prompt formatting utilities for sector and theme analysis.

Provides functions to format prompts with market data and retrieve
schema/parameter configurations from YAML templates.
"""

from typing import Any, List

from .loader import load_prompt


def format_sector_prompt(regime: str = "unknown") -> str:
    """
    Format the sector analysis prompt with market regime.

    Args:
        regime: Market regime ("crisis", "bear", "bull", "sideways", "recovery").

    Returns:
        Formatted prompt string ready for LLM.
    """
    config = load_prompt("sector_analysis")
    system_prompt = config.get("system_prompt", "")
    user_template = config.get("user_prompt_template", "")
    defaults = config.get("default_values", {})

    # Use provided regime or default
    regime_value = regime if regime else defaults.get("regime", "unknown")

    # Format user prompt
    user_prompt = user_template.format(regime=regime_value)

    # Combine system and user prompts
    return f"{system_prompt}\n\n{user_prompt}"


def format_theme_prompt(sectors: List[str], regime: str = "unknown") -> str:
    """
    Format the theme analysis prompt with selected sectors and regime.

    Args:
        sectors: List of selected sectors to analyze.
        regime: Market regime for context.

    Returns:
        Formatted prompt string ready for LLM.
    """
    config = load_prompt("theme_analysis")
    system_prompt = config.get("system_prompt", "")
    user_template = config.get("user_prompt_template", "")
    defaults = config.get("default_values", {})

    # Use provided values or defaults
    sectors_value = sectors if sectors else defaults.get("sectors", [])
    regime_value = regime if regime else defaults.get("regime", "unknown")

    # Format sectors as comma-separated string
    sectors_str = ", ".join(sectors_value) if sectors_value else "No sectors selected"

    # Format user prompt
    user_prompt = user_template.format(sectors=sectors_str, regime=regime_value)

    # Combine system and user prompts
    return f"{system_prompt}\n\n{user_prompt}"


def get_sector_response_schema() -> dict[str, Any]:
    """
    Get the JSON schema for sector analysis structured output.

    Returns:
        JSON schema dictionary for validating LLM responses.
    """
    config = load_prompt("sector_analysis")
    return config.get("response_schema", {})


def get_theme_response_schema() -> dict[str, Any]:
    """
    Get the JSON schema for theme analysis structured output.

    Returns:
        JSON schema dictionary for validating LLM responses.
    """
    config = load_prompt("theme_analysis")
    return config.get("response_schema", {})


def get_sector_model_parameters() -> dict[str, Any]:
    """
    Get model generation parameters for sector analysis.

    Returns:
        Dictionary of model parameters (max_new_tokens, temperature, etc.).
    """
    config = load_prompt("sector_analysis")
    return config.get("model_parameters", {})


def get_theme_model_parameters() -> dict[str, Any]:
    """
    Get model generation parameters for theme analysis.

    Returns:
        Dictionary of model parameters (max_new_tokens, temperature, etc.).
    """
    config = load_prompt("theme_analysis")
    return config.get("model_parameters", {})
