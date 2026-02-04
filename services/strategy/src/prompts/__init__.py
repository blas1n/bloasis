"""
Prompt management for Strategy service agents.

This module provides:
- YAML-based prompt loading with caching (via shared.prompts)
- Prompt formatting for macro strategist, technical analyst, and risk manager (formatter.py)

Future extensions:
- Remote prompt storage (S3, database)
- Prompt versioning and A/B testing
- Hot reloading
"""

from pathlib import Path
from typing import Any

from shared.prompts import PromptLoader

from .formatter import (
    format_macro_prompt,
    format_regime_risk_prompt,
    format_risk_prompt,
    format_technical_prompt,
    get_macro_model_parameters,
    get_macro_response_schema,
    get_regime_risk_model_parameters,
    get_risk_model_parameters,
    get_risk_response_schema,
    get_technical_model_parameters,
    get_technical_response_schema,
)

# Default prompts directory for this service
_PROMPTS_DIR = Path(__file__).parent

# Default loader instance for this service
_default_loader: PromptLoader | None = None


def get_loader() -> PromptLoader:
    """Get the default prompt loader instance for this service."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader(_PROMPTS_DIR)
    return _default_loader


def load_prompt(name: str) -> dict[str, Any]:
    """
    Load a prompt using the default loader.

    Args:
        name: Prompt file name without extension.

    Returns:
        Parsed prompt configuration.
    """
    return get_loader().load(name)


__all__ = [
    # Loader
    "PromptLoader",
    "get_loader",
    "load_prompt",
    # Formatter - Macro Strategist
    "format_macro_prompt",
    "format_regime_risk_prompt",
    "get_macro_response_schema",
    "get_macro_model_parameters",
    "get_regime_risk_model_parameters",
    # Formatter - Technical Analyst
    "format_technical_prompt",
    "get_technical_response_schema",
    "get_technical_model_parameters",
    # Formatter - Risk Manager
    "format_risk_prompt",
    "get_risk_response_schema",
    "get_risk_model_parameters",
]
