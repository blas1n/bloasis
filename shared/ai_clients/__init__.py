"""Shared AI clients for LLM integration.

Provides:
- LLMClient: Unified LLM client (litellm) — supports Anthropic, Ollama, OpenAI, etc.
"""

from .llm_client import LLMClient

__all__ = [
    "LLMClient",
]
