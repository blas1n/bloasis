"""Runtime helpers — env-loaded settings and side-effecting clients.

Contents (added per PR):
  - llm: provider-agnostic LLM client via LiteLLM (PR1)
  - secrets/clients for Finnhub, Alpaca will land in PR2 / PR6.
"""

from bloasis.runtime.llm import LLMSettings, complete

__all__ = ["LLMSettings", "complete"]
