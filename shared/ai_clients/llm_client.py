"""LiteLLM-based unified LLM client.

Supports any provider via litellm model routing:
- anthropic/claude-haiku-4-5-20251001  → Anthropic
- ollama_chat/llama3.1:8b              → Local Ollama
- openai/gpt-4o-mini                   → OpenAI

API key can be passed explicitly via api_key parameter or read from env by litellm.
"""

import json
from typing import Any

import litellm
import structlog

logger = structlog.get_logger(__name__)

# Suppress noisy litellm debug logs
litellm.suppress_debug_info = True


class LLMClient:
    """Unified LLM client powered by litellm.

    Drop-in replacement for ClaudeClient with identical analyze() interface.
    """

    def __init__(
        self,
        model: str = "anthropic/claude-haiku-4-5-20251001",
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialize LLM client.

        Args:
            model: LiteLLM model identifier (e.g. "anthropic/claude-haiku-4-5-20251001",
                   "ollama_chat/llama3.1:8b").
            api_base: Custom API endpoint (required for Ollama, optional otherwise).
            api_key: API key passed directly to litellm. If None, litellm reads
                     from provider-specific env vars (ANTHROPIC_API_KEY, etc.).
        """
        self.default_model = model
        self.api_base = api_base
        self.api_key = api_key
        self.max_tokens = 4096

    async def analyze(
        self,
        prompt: str,
        model: str | None = None,
        response_format: str = "json",
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> Any:
        """Analyze data using an LLM.

        Args:
            prompt: Analysis prompt.
            model: LiteLLM model to use (defaults to self.default_model).
            response_format: Expected response format ("json" or "text").
            max_tokens: Maximum tokens to generate.
            system_prompt: Optional system prompt for context.

        Returns:
            Analysis result (dict if JSON, str if text).

        Raises:
            Exception: If LLM API call fails.
        """
        model = model or self.default_model
        max_tokens = max_tokens or self.max_tokens
        system = system_prompt or "You are a financial analysis expert."

        logger.info("llm_call", model=model, prompt_length=len(prompt))

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        # Build optional kwargs
        kwargs: dict[str, Any] = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                **kwargs,
            )

            content = response.choices[0].message.content
            if content is None:
                raise ValueError("No text content in response")

            logger.info("llm_call_successful")

            if response_format == "json":
                return self._parse_json(content)

            return content

        except Exception as e:
            logger.error("llm_api_error", error=str(e))
            raise

    @staticmethod
    def _parse_json(content: str) -> Any:
        """Extract and parse JSON from LLM response.

        Handles responses wrapped in markdown code blocks.

        Args:
            content: Raw text from LLM.

        Returns:
            Parsed JSON object.
        """
        text = content.strip()

        # Try to extract JSON from markdown code blocks
        if "```json" in text:
            json_start = text.find("```json") + 7
            json_end = text.find("```", json_start)
            text = text[json_start:json_end].strip()
        elif "```" in text:
            json_start = text.find("```") + 3
            json_end = text.find("```", json_start)
            text = text[json_start:json_end].strip()

        return json.loads(text)
