"""
FinGPT Client wrapper for market regime classification.

This module wraps the shared FinGPT client with Market-regime-specific
methods for regime classification.
"""

import logging
from typing import Any

from shared.ai_clients import FinGPTClient as SharedFinGPTClient
from shared.ai_clients import MockFinGPTClient as SharedMockFinGPTClient

from ..prompts import (
    format_classification_prompt,
    get_model_parameters,
    get_response_schema,
)

logger = logging.getLogger(__name__)


class FinGPTClient:
    """
    Client wrapper for FinGPT market regime classification.

    Wraps the shared FinGPT client with regime-specific methods.

    Features:
    - YAML-based prompt management for maintainability
    - Structured output support via JSON schema
    - Configurable model and parameters
    """

    def __init__(
        self,
        api_key: str,
        model: str = "FinGPT/fingpt-sentiment_llama2-13b_lora",
        timeout: float = 60.0,
    ) -> None:
        """
        Initialize the FinGPT client wrapper.

        Args:
            api_key: Hugging Face API token for authentication.
            model: FinGPT model ID on Hugging Face.
            timeout: Request timeout in seconds.
        """
        self._client = SharedFinGPTClient(api_key=api_key, model=model, timeout=timeout)
        logger.info(f"FinGPT client wrapper initialized (model: {model})")

    async def connect(self) -> None:
        """Initialize HTTP client (no-op, client is auto-initialized)."""
        logger.info("FinGPT client wrapper connected")

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.close()
        logger.info("FinGPT client wrapper disconnected")

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
        schema = get_response_schema()
        params = get_model_parameters()

        try:
            # Use shared client's analyze method
            result = await self._client.analyze(prompt=prompt, schema=schema, params=params)
            return self._parse_regime_response(result)
        except Exception as e:
            logger.error(f"FinGPT regime classification failed: {e}")
            # Return default on error
            return {
                "regime": "sideways",
                "confidence": 0.5,
                "reasoning": f"Error: {str(e)}",
                "indicators": [],
            }

    def _parse_regime_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse regime classification response.

        Args:
            data: Parsed JSON from FinGPT

        Returns:
            Validated regime response
        """
        try:
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

        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse FinGPT response: {e}")
            return {
                "regime": "sideways",
                "confidence": 0.5,
                "reasoning": "Parse error",
                "indicators": [],
            }

    async def health_check(self) -> bool:
        """Check if Hugging Face API is accessible."""
        try:
            # Simple test using shared client
            await self._client.analyze(prompt="test", schema=None, params={"max_new_tokens": 1})
            return True
        except Exception:
            return False


class MockFinGPTClient(FinGPTClient):
    """Mock client wrapper for testing without API calls."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        timeout: float = 30.0,
    ) -> None:
        """Initialize mock client wrapper."""
        # Don't call parent __init__, use shared mock instead
        self._client = SharedMockFinGPTClient()
        logger.info("MockFinGPTClient wrapper initialized (no actual connection)")

    async def connect(self) -> None:
        """No-op for mock client."""
        logger.info("MockFinGPTClient wrapper connected (no actual connection)")

    async def close(self) -> None:
        """No-op for mock client."""
        await self._client.close()

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
