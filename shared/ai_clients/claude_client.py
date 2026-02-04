"""Claude API client for complex reasoning tasks.

Claude is used for tasks requiring sophisticated analysis:
- Technical analysis with multi-factor synthesis
- Risk assessment with nuanced judgment
- Complex reasoning about market conditions

Note: This is a generic client. Business logic (prompts, data formatting)
should be in service-specific agents, not here.
"""

import json
import logging
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, TextBlock

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Client for Claude API integration.

    Claude is used for complex reasoning tasks that require
    sophisticated analysis and nuanced judgment.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize Claude client.

        Args:
            api_key: Claude API key
        """
        self.api_key = api_key

        if not self.api_key:
            logger.warning("Claude API key not configured")
            self.client = None
        else:
            self.client = AsyncAnthropic(api_key=self.api_key)

        self.default_model = "claude-sonnet-4-20250514"
        self.max_tokens = 4096

    async def analyze(
        self,
        prompt: str,
        model: str | None = None,
        response_format: str = "json",
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> Any:
        """Analyze data using Claude.

        Args:
            prompt: Analysis prompt
            model: Claude model to use (defaults to claude-sonnet-4)
            response_format: Expected response format ("json" or "text")
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt for context

        Returns:
            Analysis result (dict if JSON, str if text)

        Raises:
            ValueError: If API key not configured
            Exception: If API request fails
        """
        if not self.client:
            raise ValueError("Claude API key not configured")

        model = model or self.default_model
        max_tokens = max_tokens or self.max_tokens

        logger.info(f"Calling Claude API: model={model}, prompt_length={len(prompt)}")

        try:
            # Build message
            messages: list[MessageParam] = [{"role": "user", "content": prompt}]

            # Add system prompt if provided
            system = system_prompt or "You are a financial analysis expert."

            # Call Claude API
            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )

            # Extract content - handle ThinkingBlock vs TextBlock
            content = None
            for block in response.content:
                if isinstance(block, TextBlock):
                    content = block.text
                    break

            if content is None:
                raise ValueError("No text content in response")

            logger.info("Claude API call successful")

            # Parse JSON if requested
            if response_format == "json":
                # Try to extract JSON from markdown code blocks if present
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()

                return json.loads(content)

            return content

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise
