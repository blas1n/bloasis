"""Layer 3: Risk Manager using Claude.

The Risk Manager evaluates trading signals for risk compliance using Claude's
sophisticated judgment to assess portfolio risk and approve/reject signals.
"""

import logging

from shared.ai_clients import ClaudeClient

from ..prompts import format_risk_prompt, get_risk_model_parameters
from ..workflow.state import MarketContext, RiskAssessment, TechnicalSignal

logger = logging.getLogger(__name__)


class RiskManager:
    """Layer 3: Claude-based risk assessment.

    Evaluates trading signals for risk compliance and portfolio safety
    using Claude's nuanced judgment capabilities.
    """

    def __init__(self, claude_client: ClaudeClient):
        """Initialize Risk Manager.

        Args:
            claude_client: Claude client instance
        """
        self.claude = claude_client

    async def assess(
        self,
        signals: list[TechnicalSignal],
        market_context: MarketContext,
        user_preferences: dict,
    ) -> RiskAssessment:
        """Perform risk assessment on technical signals.

        Args:
            signals: Technical signals from Layer 2
            market_context: Macro context from Layer 1
            user_preferences: User investment preferences

        Returns:
            RiskAssessment with approval decision
        """
        logger.info(f"Starting risk assessment for {len(signals)} signals")

        # Prepare data for Claude
        signals_data = self._prepare_signals_data(signals)
        market_context_dict = {
            "regime": market_context.regime,
            "risk_level": market_context.risk_level,
        }

        try:
            # Get formatted prompt from YAML
            system_prompt, user_prompt = format_risk_prompt(
                signals=signals_data,
                market_context=market_context_dict,
                user_preferences=user_preferences,
            )

            # Get model parameters from YAML
            model_params = get_risk_model_parameters()

            # Call Claude for risk assessment using generic analyze method
            response = await self.claude.analyze(
                prompt=user_prompt,
                system_prompt=system_prompt,
                response_format="json",
                max_tokens=model_params.get("max_tokens", 4000),
            )

            # Validate response type
            if not isinstance(response, dict):
                logger.error(f"Expected dict response, got {type(response)}")
                raise ValueError("Invalid response type from Claude")

            # Build RiskAssessment
            assessment = RiskAssessment(
                approved=response.get("approved", False),
                risk_score=float(response.get("risk_score", 1.0)),
                position_adjustments=response.get("position_adjustments", {}),
                warnings=response.get("warnings", []),
                concentration_risk=float(response.get("concentration_risk", 0.0)),
            )

            logger.info(
                f"Risk assessment complete: approved={assessment.approved}, "
                f"risk_score={assessment.risk_score:.2f}"
            )
            return assessment

        except Exception as e:
            logger.error(f"Risk assessment failed: {e}", exc_info=True)

            # Fail-safe: Reject on error
            logger.warning("Rejecting signals due to risk assessment failure (fail-safe)")
            return RiskAssessment(
                approved=False,
                risk_score=1.0,
                position_adjustments={},
                warnings=[f"Risk assessment error: {str(e)}"],
                concentration_risk=1.0,
            )

    def _prepare_signals_data(self, signals: list[TechnicalSignal]) -> list[dict]:
        """Prepare signals data for Claude analysis.

        Args:
            signals: Technical signals

        Returns:
            Formatted signals data
        """
        signals_data = []

        for signal in signals:
            signals_data.append(
                {
                    "symbol": signal.symbol,
                    "direction": signal.direction,
                    "strength": signal.strength,
                    "entry_price": float(signal.entry_price),
                    "rationale": signal.rationale,
                }
            )

        return signals_data

    def _check_sector_concentration(
        self, signals: list[TechnicalSignal], max_concentration: float = 0.5
    ) -> tuple[bool, float]:
        """Check if sector concentration exceeds limits.

        Args:
            signals: Trading signals
            max_concentration: Maximum sector concentration (0-1)

        Returns:
            Tuple of (exceeds_limit, concentration_ratio)
        """
        if not signals:
            return False, 0.0

        # Count signals per sector (would need sector info from signals)
        # For now, return conservative estimate
        total_signals = len(signals)
        if total_signals <= 3:
            return False, 1.0 / total_signals

        # Conservative: assume worst case
        concentration = 0.4
        return concentration > max_concentration, concentration
