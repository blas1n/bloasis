"""Layer 1: Macro Strategist using FinGPT.

The Macro Strategist provides macro economic context and risk assessment
using FinGPT's financial domain expertise.
"""

import logging
from typing import Any

from shared.ai_clients import FinGPTClient

from ..prompts import (
    format_macro_prompt,
    format_regime_risk_prompt,
    get_macro_model_parameters,
    get_regime_risk_model_parameters,
)
from ..workflow.state import MarketContext

logger = logging.getLogger(__name__)


class MacroStrategist:
    """Layer 1: FinGPT-based macro economic analysis.

    Analyzes macro environment and provides risk context for trading decisions.
    Uses FinGPT for cost-effective financial domain analysis.
    """

    def __init__(self, fingpt_client: FinGPTClient):
        """Initialize Macro Strategist.

        Args:
            fingpt_client: FinGPT client instance
        """
        self.fingpt = fingpt_client

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
            # Call FinGPT for analysis
            # Note: shared FinGPT client uses schema and params parameters
            response = await self.fingpt.analyze(
                prompt=prompt,
                schema=None,  # Let FinGPT return raw JSON
                params=model_params,
            )

            # Validate response type
            if not isinstance(response, dict):
                logger.error(f"Expected dict response, got {type(response)}")
                raise ValueError("Invalid response type from FinGPT")

            # Build MarketContext
            market_context = MarketContext(
                regime=regime,
                confidence=0.8,  # FinGPT confidence
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
            logger.warning("Using fallback market context due to analysis failure")
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
        # Get formatted prompt from YAML
        system_prompt, user_prompt = format_regime_risk_prompt(
            regime=regime,
            indicators=indicators,
        )
        prompt = f"{system_prompt}\n\n{user_prompt}"

        # Get model parameters from YAML
        model_params = get_regime_risk_model_parameters()

        try:
            return await self.fingpt.analyze(
                prompt=prompt,
                schema=None,
                params=model_params,
            )
        except Exception as e:
            logger.error(f"Regime risk assessment failed: {e}")
            return {
                "confidence": 0.5,
                "risk_level": "medium",
                "factors": ["assessment_error"],
            }
