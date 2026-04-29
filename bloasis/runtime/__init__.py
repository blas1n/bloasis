"""Runtime helpers — env-loaded settings and side-effecting clients.

Contents:
  - llm:  provider-agnostic LLM client via LiteLLM
  - halt: live-trading halt-condition gate (rolling realized PnL)
"""

from bloasis.runtime.halt import HaltDecision, evaluate_halt
from bloasis.runtime.llm import LLMSettings, complete

__all__ = ["HaltDecision", "LLMSettings", "complete", "evaluate_halt"]
