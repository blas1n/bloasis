"""Shared AI clients for LLM integration.

This module provides reusable AI client implementations that can be used
across multiple services in BLOASIS.

Key clients:
- LLMClient: Unified LLM client (litellm) — supports Anthropic, Ollama, OpenAI, etc.
- ClaudeClient: Backward-compatible alias for Anthropic Claude usage.
"""

from .claude_client import ClaudeClient
from .llm_client import LLMClient

__all__ = [
    "LLMClient",
    "ClaudeClient",
]
