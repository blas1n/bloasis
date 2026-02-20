"""Layer 1: Macro Strategist using Claude.

The Macro Strategist provides macro economic context and risk assessment
using Claude's AI capabilities.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..prompts import (
    format_macro_prompt,
    format_regime_risk_prompt,
    get_macro_model_parameters,
    get_regime_risk_model_parameters,
)
from ..workflow.state import MarketContext

if TYPE_CHECKING:
    from shared.ai_clients import ClaudeClient

logger = logging.getLogger(__name__)


class MacroStrategist:
    """Layer 1: Claude-based macro economic analysis.

    Analyzes macro environment and provides risk context for trading decisions.
    """

    def __init__(self, analyst: "ClaudeClient") -> None:
        """Initialize Macro Strategist.

        Args:
            analyst: Claude client instance (required).
        """
        self.analyst = analyst

    async def analyze(
        self,
        stock_picks: list[dict],
        regime: str,
        user_preferences: dict,
    ) -> MarketContext:
        """Perform macro economic analysis.

        Args:
            stock_picks: Stock picks from Stage 3 (Factor Scoring)
            regime: Current market regime
            user_preferences: User investment preferences

        Returns:
            MarketContext with macro analysis results

        Raises:
            Exception: If Claude API call fails.
        """
        logger.info(f"Starting macro analysis for {len(stock_picks)} stocks in {regime} regime")

        symbols = [pick["symbol"] for pick in stock_picks]
        sectors = list(set(pick["sector"] for pick in stock_picks))

        system_prompt, user_prompt = format_macro_prompt(
            symbols=symbols,
            regime=regime,
            sectors=sectors,
        )
        prompt = f"{system_prompt}\n\n{user_prompt}"
        model_params = get_macro_model_parameters()

        response = await self.analyst.analyze(
            prompt=prompt,
            model=model_params.get("model", "claude-haiku-4-5-20251001"),
            response_format="json",
            max_tokens=model_params.get("max_tokens", model_params.get("max_new_tokens", 500)),
        )

        if not isinstance(response, dict):
            raise ValueError(f"Expected dict response from Claude, got {type(response)}")

        market_context = MarketContext(
            regime=regime,
            confidence=0.8,
            risk_level=response.get("risk_level", "medium"),
            sector_outlook=response.get("sector_outlook", {}),
            macro_indicators=response.get("macro_indicators", {}),
        )

        logger.info(
            f"Macro analysis complete: risk_level={market_context.risk_level}, "
            f"sectors={len(market_context.sector_outlook)}"
        )
        return market_context

    async def assess_regime_risk(self, regime: str, indicators: dict[str, Any]) -> dict[str, Any]:
        """Assess risk level for current regime.

        Args:
            regime: Market regime
            indicators: Macro economic indicators

        Returns:
            Risk assessment dictionary

        Raises:
            Exception: If Claude API call fails.
        """
        system_prompt, user_prompt = format_regime_risk_prompt(
            regime=regime,
            indicators=indicators,
        )
        prompt = f"{system_prompt}\n\n{user_prompt}"
        model_params = get_regime_risk_model_parameters()

        return await self.analyst.analyze(
            prompt=prompt,
            model=model_params.get("model", "claude-haiku-4-5-20251001"),
            response_format="json",
            max_tokens=model_params.get("max_tokens", model_params.get("max_new_tokens", 500)),
        )
