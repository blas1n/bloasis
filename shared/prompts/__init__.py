"""
Shared prompt management utilities for BLOASIS services.

This module provides:
- YAML-based prompt loading with caching (loader.py)
- Base utilities for prompt formatting (base.py)

Usage:
    from shared.prompts import PromptLoader

    # Create a loader for your service's prompts directory
    loader = PromptLoader(Path("/path/to/prompts"))

    # Load a prompt configuration
    config = loader.load("sector_analysis")

    # Access prompt components
    system_prompt = config.get("system_prompt", "")
    user_template = config.get("user_prompt_template", "")

Future extensions:
- Remote prompt storage (S3, database)
- Prompt versioning and A/B testing
- Hot reloading
"""

from .base import format_prompt, get_model_parameters, get_response_schema
from .loader import PromptLoader, clear_prompt_cache

__all__ = [
    # Loader
    "PromptLoader",
    "clear_prompt_cache",
    # Base utilities
    "format_prompt",
    "get_response_schema",
    "get_model_parameters",
]
