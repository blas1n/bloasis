"""Layer 1: Macro Strategist using Claude.

The Macro Strategist provides macro economic context and risk assessment
using Claude's AI capabilities with rule-based fallback.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from ..config import config
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
    Falls back to rule-based defaults when no API key is configured.
    """

    def __init__(self, analyst: Optional["ClaudeClient"] = None):
        """Initialize Macro Strategist.

        Args:
            analyst: Optional Claude client. If None, attempts to create one
                     from config. Falls back to rule-based defaults if no API key.
        """
        if analyst is not None:
            self.analyst = analyst
        elif config.anthropic_api_key:
            from shared.ai_clients import ClaudeClient

            self.analyst: ClaudeClient | None = ClaudeClient(
                api_key=config.anthropic_api_key
            )
        else:
            self.analyst = None
            logger.warning("No ANTHROPIC_API_KEY set — macro analysis uses rule-based fallback")

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
        """
        logger.info(f"Starting macro analysis for {len(stock_picks)} stocks in {regime} regime")

        # Extract symbols and sectors
        symbols = [pick["symbol"] for pick in stock_picks]
        sectors = list(set(pick["sector"] for pick in stock_picks))

        if self.analyst:
            # Get formatted prompt from YAML
            system_prompt, user_prompt = format_macro_prompt(
                symbols=symbols,
                regime=regime,
                sectors=sectors,
            )
            prompt = f"{system_prompt}\n\n{user_prompt}"

            # Get model parameters from YAML
            model_params = get_macro_model_parameters()

            try:
                response = await self.analyst.analyze(
                    prompt=prompt,
                    model=model_params.get("model", "claude-haiku-4-5-20251001"),
                    response_format="json",
                    max_tokens=model_params.get(
                        "max_tokens", model_params.get("max_new_tokens", 500)
                    ),
                )

                # Validate response type
                if not isinstance(response, dict):
                    logger.error(f"Expected dict response, got {type(response)}")
                    raise ValueError("Invalid response type from Claude")

                # Build MarketContext
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

            except Exception as e:
                logger.error(f"Macro analysis failed: {e}", exc_info=True)

        # Fallback to safe defaults
        logger.warning("Using fallback market context (rule-based)")
        return MarketContext(
            regime=regime,
            confidence=0.5,
            risk_level="medium",
            sector_outlook={sector: 50.0 for sector in sectors},
            macro_indicators={"status": "fallback"},
        )

    async def assess_regime_risk(self, regime: str, indicators: dict[str, Any]) -> dict[str, Any]:
        """Assess risk level for current regime.

        Args:
            regime: Market regime
            indicators: Macro economic indicators

        Returns:
            Risk assessment dictionary
        """
        if self.analyst:
            # Get formatted prompt from YAML
            system_prompt, user_prompt = format_regime_risk_prompt(
                regime=regime,
                indicators=indicators,
            )
            prompt = f"{system_prompt}\n\n{user_prompt}"

            # Get model parameters from YAML
            model_params = get_regime_risk_model_parameters()

            try:
                return await self.analyst.analyze(
                    prompt=prompt,
                    model=model_params.get("model", "claude-haiku-4-5-20251001"),
                    response_format="json",
                    max_tokens=model_params.get(
                        "max_tokens", model_params.get("max_new_tokens", 500)
                    ),
                )
            except Exception as e:
                logger.error(f"Regime risk assessment failed: {e}")

        return {
            "confidence": 0.5,
            "risk_level": "medium",
            "factors": ["assessment_error"],
        }
