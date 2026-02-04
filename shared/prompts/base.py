"""
Base utilities for prompt formatting.

Provides generic helper functions for working with prompt configurations
loaded from YAML files.
"""

from typing import Any


def format_prompt(
    config: dict[str, Any],
    variables: dict[str, Any],
    system_key: str = "system_prompt",
    user_template_key: str = "user_prompt_template",
    defaults_key: str = "default_values",
) -> tuple[str, str]:
    """
    Format a prompt configuration with variables.

    This is a generic utility for formatting prompts from YAML configs.
    Services may use this directly or create their own specialized formatters.

    Args:
        config: Loaded prompt configuration from YAML.
        variables: Dictionary of variable values to substitute.
        system_key: Key for system prompt in config.
        user_template_key: Key for user prompt template in config.
        defaults_key: Key for default values in config.

    Returns:
        Tuple of (system_prompt, user_prompt).

    Example:
        config = loader.load("macro_strategist")
        system_prompt, user_prompt = format_prompt(
            config,
            {"symbols": "AAPL, MSFT", "regime": "bull"}
        )
    """
    system_prompt = config.get(system_key, "")
    user_template = config.get(user_template_key, "")
    defaults = config.get(defaults_key, {})

    # Merge defaults with provided variables (provided values override defaults)
    merged_vars = {**defaults, **variables}

    # Format user prompt with variables
    try:
        user_prompt = user_template.format(**merged_vars)
    except KeyError as e:
        raise KeyError(
            f"Missing variable {e} in prompt template. "
            f"Available: {list(merged_vars.keys())}"
        )

    return system_prompt.strip(), user_prompt.strip()


def get_response_schema(config: dict[str, Any]) -> dict[str, Any]:
    """
    Get the JSON schema for structured output from a prompt config.

    Args:
        config: Loaded prompt configuration from YAML.

    Returns:
        JSON schema dictionary for validating LLM responses.
    """
    return config.get("response_schema", {})


def get_model_parameters(config: dict[str, Any]) -> dict[str, Any]:
    """
    Get model generation parameters from a prompt config.

    Args:
        config: Loaded prompt configuration from YAML.

    Returns:
        Dictionary of model parameters (max_new_tokens, temperature, etc.).
    """
    return config.get("model_parameters", {})
