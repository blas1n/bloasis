"""Shared AI clients for Claude API integration.

This module provides reusable AI client implementations that can be used
across multiple services in BLOASIS.

Key clients:
- ClaudeClient: Claude API client for AI-powered analysis tasks
"""

from .claude_client import ClaudeClient

__all__ = [
    "ClaudeClient",
]
