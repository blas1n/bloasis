"""
Prompt management for FinGPT sector and theme analysis.

This module provides:
- YAML-based prompt loading with caching (loader.py)
- Prompt formatting for sector and theme analysis (formatter.py)

Future extensions:
- Remote prompt storage (S3, database)
- Prompt versioning and A/B testing
- Hot reloading
"""

from .formatter import (
    format_sector_prompt,
    format_theme_prompt,
    get_sector_model_parameters,
    get_sector_response_schema,
    get_theme_model_parameters,
    get_theme_response_schema,
)
from .loader import PromptLoader, get_loader, load_prompt

__all__ = [
    # Loader
    "PromptLoader",
    "get_loader",
    "load_prompt",
    # Formatter
    "format_sector_prompt",
    "format_theme_prompt",
    "get_sector_response_schema",
    "get_theme_response_schema",
    "get_sector_model_parameters",
    "get_theme_model_parameters",
]
