"""
Prompt management for FinGPT classification.

This module provides:
- YAML-based prompt loading with caching (loader.py)
- Prompt formatting with market data (formatter.py)

Future extensions:
- Remote prompt storage (S3, database)
- Prompt versioning and A/B testing
- Hot reloading
"""

from .formatter import (
    format_classification_prompt,
    get_classification_prompt,
    get_model_parameters,
    get_response_schema,
)
from .loader import PromptLoader, get_loader, load_prompt

__all__ = [
    # Loader
    "PromptLoader",
    "get_loader",
    "load_prompt",
    # Formatter
    "get_classification_prompt",
    "format_classification_prompt",
    "get_response_schema",
    "get_model_parameters",
]
