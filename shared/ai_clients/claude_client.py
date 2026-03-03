"""Backward-compatible Claude API client.

ClaudeClient is now a thin alias for LLMClient.
Kept for backward compatibility with existing tests and external code.
New code should use LLMClient directly.
"""

from .llm_client import LLMClient


class ClaudeClient(LLMClient):
    """Claude-specific LLMClient alias (backward compatibility).

    Defaults to anthropic/claude-sonnet-4-20250514 and auto-prefixes
    bare Claude model names with "anthropic/".
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize Claude client.

        Args:
            api_key: Passed to litellm. If None, litellm reads
                     ANTHROPIC_API_KEY from env automatically.
        """
        super().__init__(model="anthropic/claude-sonnet-4-20250514", api_key=api_key)

    async def analyze(
        self,
        prompt: str,
        model: str | None = None,
        response_format: str = "json",
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ):
        """Analyze data using Claude via litellm.

        Auto-prefixes bare Claude model names
        (e.g. "claude-haiku-4-5-20251001" → "anthropic/claude-haiku-4-5-20251001").
        """
        if model and "/" not in model:
            model = f"anthropic/{model}"

        return await super().analyze(
            prompt=prompt,
            model=model,
            response_format=response_format,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )
