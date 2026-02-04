"""FinGPT client for financial analysis via Hugging Face API.

Provides both real Hugging Face API client and mock client for development.

This is a generic client that can be used across multiple services for
various financial analysis tasks (market regime, sector analysis, etc.).
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Hugging Face Inference API endpoint
HF_INFERENCE_API_URL = "https://api-inference.huggingface.co/models"

# Default FinGPT model
DEFAULT_MODEL = "FinGPT/fingpt-sentiment_llama2-13b_lora"


class FinGPTClientBase(ABC):
    """Base class for FinGPT clients."""

    @abstractmethod
    async def analyze(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze financial data using FinGPT.

        Args:
            prompt: Analysis prompt
            schema: Optional JSON schema for structured output
            params: Optional model parameters (temperature, max_tokens, etc.)

        Returns:
            Analysis result as dictionary
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close client connections."""
        pass


class FinGPTClient(FinGPTClientBase):
    """Real FinGPT client using Hugging Face Inference API.

    Features:
    - Structured output support via JSON schema
    - Configurable model and parameters
    - Async HTTP client with connection pooling
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
    ):
        """Initialize FinGPT client.

        Args:
            api_key: Hugging Face API token
            model: Model ID (default: FinGPT sentiment model)
            timeout: Request timeout in seconds
        """
        if not api_key:
            raise ValueError("Hugging Face API token required for FinGPT client")

        self.api_key = api_key
        self.model = model
        self.timeout = timeout

        self.client = httpx.AsyncClient(
            base_url=HF_INFERENCE_API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        logger.info(f"FinGPT client initialized (model: {self.model})")

    async def analyze(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze financial data using FinGPT with optional structured output.

        Args:
            prompt: Analysis prompt
            schema: Optional JSON schema for structured output
            params: Optional model parameters (temperature, max_tokens, etc.)

        Returns:
            Analysis result as dictionary

        Raises:
            RuntimeError: If API request fails
        """
        # Default parameters
        default_params = {
            "max_new_tokens": 500,
            "temperature": 0.1,
            "top_p": 0.9,
            "do_sample": False,
            "return_full_text": False,
        }

        # Merge with provided params
        request_params = {**default_params, **(params or {})}

        # Add structured output grammar if schema provided
        if schema:
            request_params["grammar"] = {"type": "json", "value": schema}

        try:
            response = await self.client.post(
                f"/{self.model}",
                json={"inputs": prompt, "parameters": request_params},
            )
            response.raise_for_status()

            result = response.json()
            generated_text = (
                result[0]["generated_text"] if isinstance(result, list) else result
            )

            # Parse JSON response
            return self._parse_json_response(generated_text)

        except httpx.HTTPStatusError as e:
            # If grammar not supported (422), could retry without it
            if e.response.status_code == 422 and schema:
                logger.warning(
                    "Model doesn't support grammar, retrying without structured output"
                )
                return await self.analyze(prompt, schema=None, params=params)

            logger.error(f"Hugging Face API error: {e.response.status_code}")
            raise RuntimeError(f"Hugging Face API error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Hugging Face request failed: {e}")
            raise RuntimeError(f"Hugging Face request failed: {e}")
        except Exception as e:
            logger.error(f"FinGPT analysis failed: {e}")
            raise

    def _parse_json_response(self, text: str | dict) -> dict[str, Any]:
        """Parse JSON from generated text.

        Args:
            text: Generated text or dict from API

        Returns:
            Parsed JSON dictionary
        """
        # If already a dict, return it
        if isinstance(text, dict):
            return text

        # Find JSON in text (may have extra text before/after)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = text[start:end]
            return json.loads(json_str)

        # If no JSON found, return empty dict
        logger.warning(f"No valid JSON found in response: {text[:100]}...")
        return {}

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
        logger.info("FinGPT client closed")


class MockFinGPTClient(FinGPTClientBase):
    """Mock FinGPT client for development and testing.

    Uses rule-based logic to generate realistic analysis results without
    making actual API calls.
    """

    def __init__(self):
        """Initialize mock client."""
        logger.info("MockFinGPT client initialized (no API calls)")

    async def analyze(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate mock analysis based on prompt keywords.

        This provides basic mock behavior. Services can extend this class
        for more sophisticated mocking based on their specific needs.

        Args:
            prompt: Analysis prompt (analyzed for keywords)
            schema: Ignored in mock
            params: Ignored in mock

        Returns:
            Mock analysis result
        """
        prompt_lower = prompt.lower()

        # Simple keyword-based mock responses
        if "crisis" in prompt_lower or "vix" in prompt_lower:
            return {
                "regime": "crisis" if "crisis" in prompt_lower else "bear",
                "confidence": 0.85,
                "reasoning": "Mock analysis based on prompt keywords",
                "indicators": ["vix", "volatility"],
            }
        elif "bull" in prompt_lower:
            return {
                "regime": "bull",
                "confidence": 0.80,
                "reasoning": "Mock analysis for bullish conditions",
                "indicators": ["momentum"],
            }
        else:
            return {
                "regime": "sideways",
                "confidence": 0.70,
                "reasoning": "Mock analysis with mixed signals",
                "indicators": ["mixed"],
            }

    async def close(self) -> None:
        """No-op for mock client."""
        logger.info("MockFinGPT client closed (no resources to cleanup)")
