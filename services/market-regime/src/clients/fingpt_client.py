"""
FinGPT Client - Hugging Face API wrapper for FinGPT financial analysis.

This module provides a client for interacting with FinGPT models via
Hugging Face Inference API for market regime classification.

FinGPT models: https://huggingface.co/FinGPT
Structured outputs: https://huggingface.co/docs/inference-providers/en/guides/structured-output
"""

import json
import logging
from typing import Any, Optional

import httpx

from ..prompts import (
    format_classification_prompt,
    get_model_parameters,
    get_response_schema,
)

logger = logging.getLogger(__name__)

# Hugging Face Inference API endpoint
HF_INFERENCE_API_URL = "https://api-inference.huggingface.co/models"

# Default FinGPT model
DEFAULT_MODEL = "FinGPT/fingpt-sentiment_llama2-13b_lora"


class FinGPTClient:
    """
    Client for FinGPT financial analysis via Hugging Face.

    Provides market regime analysis using FinGPT's specialized
    financial language model capabilities hosted on Hugging Face.

    Features:
    - YAML-based prompt management for maintainability
    - Structured output support via JSON schema
    - Configurable model and parameters
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        """
        Initialize the FinGPT client.

        Args:
            api_key: Hugging Face API token for authentication.
            model: FinGPT model ID on Hugging Face.
            timeout: Request timeout in seconds.
        """
        self.api_key = api_key
        self.model = model
        self.base_url = f"{HF_INFERENCE_API_URL}/{model}"
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """Initialize HTTP client."""
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        logger.info(f"FinGPT client connected (model: {self.model})")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("FinGPT client disconnected")

    async def classify_regime(
        self,
        market_data: dict[str, Any],
        macro_indicators: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Classify market regime using FinGPT via Hugging Face.

        Args:
            market_data: Recent market data including VIX, indices, etc.
            macro_indicators: Macro economic indicators.

        Returns:
            Dictionary containing:
            - regime: Market regime classification
            - confidence: Confidence score (0.0 to 1.0)
            - reasoning: Explanation for the classification
            - indicators: Key indicators used
        """
        # Build prompt from YAML template
        prompt = format_classification_prompt(market_data, macro_indicators)
        response = await self._call_api(prompt)
        return self._parse_regime_response(response)

    async def _call_api(self, prompt: str) -> Any:
        """
        Call Hugging Face Inference API with structured output support.

        Uses JSON schema grammar for constrained generation when supported.
        """
        if not self._client:
            await self.connect()

        if self._client is None:
            raise RuntimeError("Failed to initialize HTTP client")

        # Get parameters from YAML config
        params = get_model_parameters()
        schema = get_response_schema()

        try:
            # Build request with structured output
            request_body: dict[str, Any] = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": params.get("max_new_tokens", 500),
                    "temperature": params.get("temperature", 0.1),
                    "top_p": params.get("top_p", 0.9),
                    "do_sample": params.get("do_sample", False),
                    "return_full_text": False,
                },
            }

            # Add grammar for structured output (if model supports it)
            # This uses Outlines-based constrained decoding
            request_body["parameters"]["grammar"] = {
                "type": "json",
                "value": schema,
            }

            response = await self._client.post(
                self.base_url,
                json=request_body,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            # If grammar not supported, retry without it
            if e.response.status_code == 422:
                logger.warning("Model doesn't support grammar, retrying without structured output")
                return await self._call_api_without_grammar(prompt, params)
            logger.error(f"Hugging Face API error: {e.response.status_code}")
            raise RuntimeError(f"Hugging Face API error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Hugging Face request failed: {e}")
            raise RuntimeError(f"Hugging Face request failed: {e}")

    async def _call_api_without_grammar(
        self, prompt: str, params: dict[str, Any]
    ) -> Any:
        """Fallback API call without structured output grammar."""
        if self._client is None:
            raise RuntimeError("HTTP client not initialized")

        response = await self._client.post(
            self.base_url,
            json={
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": params.get("max_new_tokens", 500),
                    "temperature": params.get("temperature", 0.1),
                    "return_full_text": False,
                },
            },
        )
        response.raise_for_status()
        return response.json()

    def _parse_regime_response(self, response: Any) -> dict[str, Any]:
        """Parse Hugging Face response into regime classification."""
        try:
            # Hugging Face returns list of generated texts
            if isinstance(response, list) and len(response) > 0:
                content = response[0].get("generated_text", "")
            elif isinstance(response, dict):
                content = response.get("generated_text", response.get("content", "{}"))
            else:
                content = str(response)

            # Try to extract JSON from response
            if isinstance(content, str):
                # Find JSON in response
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    json_str = content[start:end]
                    data = json.loads(json_str)
                else:
                    data = {}
            else:
                data = content

            # Validate and return
            regime = data.get("regime", "sideways")
            if regime not in ["crisis", "bear", "bull", "sideways", "recovery"]:
                regime = "sideways"

            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

            return {
                "regime": regime,
                "confidence": confidence,
                "reasoning": data.get("reasoning", "Unable to determine"),
                "indicators": data.get("key_indicators", []),
            }

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse FinGPT response: {e}")
            return {
                "regime": "sideways",
                "confidence": 0.5,
                "reasoning": "Parse error",
                "indicators": [],
            }

    async def health_check(self) -> bool:
        """Check if Hugging Face API is accessible."""
        if not self.api_key:
            return False
        try:
            if not self._client:
                await self.connect()
            if self._client is None:
                return False
            # Simple test query
            response = await self._client.post(
                self.base_url,
                json={"inputs": "test", "parameters": {"max_new_tokens": 1}},
            )
            # 200 OK or 503 (model loading) are acceptable
            return response.status_code in (200, 503)
        except Exception:
            return False


class MockFinGPTClient(FinGPTClient):
    """Mock client for testing without API calls."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        timeout: float = 30.0,
    ) -> None:
        """Initialize mock client (no real connection needed)."""
        self.api_key = api_key
        self.model = model or "mock-model"
        self.base_url = ""
        self.timeout = timeout
        self._client = None

    async def connect(self) -> None:
        """No-op for mock client."""
        logger.info("MockFinGPTClient initialized (no actual connection)")

    async def close(self) -> None:
        """No-op for mock client."""
        pass

    async def classify_regime(
        self,
        market_data: dict[str, Any],
        macro_indicators: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return mock classification based on simple VIX rules.

        This provides reasonable mock behavior for development and testing.
        """
        vix = market_data.get("vix", 20.0)
        yield_spread = macro_indicators.get("yield_curve_10y_2y", 0.5)

        # Simple rule-based classification
        if vix > 35:
            return {
                "regime": "crisis",
                "confidence": 0.90,
                "reasoning": f"VIX at {vix:.1f} indicates extreme fear and volatility",
                "indicators": ["vix", "volatility"],
            }
        elif vix > 25:
            return {
                "regime": "bear",
                "confidence": 0.80,
                "reasoning": f"Elevated VIX at {vix:.1f} suggests bearish conditions",
                "indicators": ["vix"],
            }
        elif yield_spread < 0:
            return {
                "regime": "bear",
                "confidence": 0.75,
                "reasoning": f"Inverted yield curve ({yield_spread:.2f}%) signals recession risk",
                "indicators": ["yield_curve"],
            }
        elif vix < 15:
            return {
                "regime": "bull",
                "confidence": 0.85,
                "reasoning": f"Low VIX at {vix:.1f} indicates bullish complacency",
                "indicators": ["vix"],
            }
        else:
            sp500_change = market_data.get("sp500_1m_change", 0)
            if sp500_change > 3:
                return {
                    "regime": "bull",
                    "confidence": 0.75,
                    "reasoning": f"Positive momentum with S&P up {sp500_change:.1f}%",
                    "indicators": ["sp500", "momentum"],
                }
            elif sp500_change < -3:
                return {
                    "regime": "bear",
                    "confidence": 0.70,
                    "reasoning": f"Negative momentum with S&P down {sp500_change:.1f}%",
                    "indicators": ["sp500", "momentum"],
                }
            else:
                return {
                    "regime": "sideways",
                    "confidence": 0.65,
                    "reasoning": "Mixed signals, range-bound market",
                    "indicators": ["vix", "sp500"],
                }

    async def health_check(self) -> bool:
        """Mock health check always returns True."""
        return True
