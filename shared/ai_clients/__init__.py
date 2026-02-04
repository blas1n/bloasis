"""Shared AI clients for FinGPT and Claude.

This module provides reusable AI client implementations that can be used
across multiple services in BLOASIS.

Key clients:
- FinGPTClient: Hugging Face-based FinGPT client for financial analysis
- MockFinGPTClient: Mock client for development and testing
- ClaudeClient: Claude API client for complex reasoning tasks
"""

from .claude_client import ClaudeClient
from .fingpt_client import FinGPTClient, FinGPTClientBase, MockFinGPTClient

__all__ = [
    "FinGPTClient",
    "FinGPTClientBase",
    "MockFinGPTClient",
    "ClaudeClient",
]
