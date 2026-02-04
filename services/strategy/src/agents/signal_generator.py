"""Layer 4: Signal Generator.

The Signal Generator creates final trading signals by combining technical signals
with risk adjustments and calculating position sizes, stop-loss, and take-profit levels.
"""

import logging
from decimal import Decimal

from ..workflow.state import MarketContext, RiskAssessment, TechnicalSignal, TradingSignal

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Layer 4: Final trading signal generation.

    Combines technical signals with risk adjustments to produce
    actionable trading signals with position sizing and risk levels.
    """

    def generate(
        self,
        technical_signals: list[TechnicalSignal],
        risk_assessment: RiskAssessment,
        market_context: MarketContext,
        user_preferences: dict,
    ) -> list[TradingSignal]:
        """Generate final trading signals.

        Args:
            technical_signals: Signals from Layer 2 (Technical Analyst)
            risk_assessment: Assessment from Layer 3 (Risk Manager)
            market_context: Context from Layer 1 (Macro Strategist)
            user_preferences: User investment preferences

        Returns:
            List of final trading signals
        """
        logger.info(f"Generating trading signals from {len(technical_signals)} technical signals")

        trading_signals = []

        for tech_signal in technical_signals:
            # Calculate position size
            base_size = self._calculate_base_size(
                tech_signal.strength,
                user_preferences.get("risk_profile", "MODERATE"),
            )

            # Apply risk adjustment
            size_multiplier = risk_assessment.position_adjustments.get(tech_signal.symbol, 1.0)
            final_size = base_size * Decimal(str(size_multiplier))

            # Calculate stop-loss and take-profit
            stop_loss, take_profit = self._calculate_levels(tech_signal, market_context)

            # Create trading signal
            trading_signal = TradingSignal(
                symbol=tech_signal.symbol,
                action=self._signal_to_action(tech_signal.direction),
                confidence=tech_signal.strength,
                size_recommendation=final_size,
                entry_price=tech_signal.entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                rationale=tech_signal.rationale,
                risk_approved=risk_assessment.approved,
            )

            trading_signals.append(trading_signal)

        logger.info(
            f"Generated {len(trading_signals)} trading signals "
            f"(risk_approved={risk_assessment.approved})"
        )
        return trading_signals

    def _calculate_base_size(self, strength: float, risk_profile: str) -> Decimal:
        """Calculate base position size based on signal strength and risk profile.

        Args:
            strength: Signal strength (0-1)
            risk_profile: User risk profile (CONSERVATIVE/MODERATE/AGGRESSIVE)

        Returns:
            Position size as decimal (0.0-1.0 of portfolio)
        """
        # Max position sizes by risk profile
        max_sizes = {
            "CONSERVATIVE": 0.05,  # 5% max
            "MODERATE": 0.10,  # 10% max
            "AGGRESSIVE": 0.15,  # 15% max
        }

        max_size = max_sizes.get(risk_profile, 0.10)

        # Scale by signal strength (use Decimal for precision)
        position_size = Decimal(str(strength)) * Decimal(str(max_size))

        return position_size.quantize(Decimal("0.0001"))

    def _calculate_levels(
        self,
        signal: TechnicalSignal,
        market_context: MarketContext,
    ) -> tuple[Decimal, Decimal]:
        """Calculate stop-loss and take-profit levels.

        Args:
            signal: Technical signal
            market_context: Market context

        Returns:
            Tuple of (stop_loss, take_profit)
        """
        entry = signal.entry_price

        # Base levels (2% stop, 5% target for long; reverse for short)
        if signal.direction == "long":
            base_stop_pct = Decimal("0.98")  # -2%
            base_target_pct = Decimal("1.05")  # +5%
        else:  # short
            base_stop_pct = Decimal("1.02")  # +2%
            base_target_pct = Decimal("0.95")  # -5%

        # Adjust for market risk level
        if market_context.risk_level == "high":
            # Tighter stops in high risk environment
            if signal.direction == "long":
                stop_loss = entry * Decimal("0.99")  # -1%
                take_profit = entry * Decimal("1.03")  # +3%
            else:
                stop_loss = entry * Decimal("1.01")  # +1%
                take_profit = entry * Decimal("0.97")  # -3%
        elif market_context.risk_level == "extreme":
            # Very tight stops in extreme risk
            if signal.direction == "long":
                stop_loss = entry * Decimal("0.995")  # -0.5%
                take_profit = entry * Decimal("1.02")  # +2%
            else:
                stop_loss = entry * Decimal("1.005")  # +0.5%
                take_profit = entry * Decimal("0.98")  # -2%
        else:
            # Normal stops for low/medium risk
            stop_loss = entry * base_stop_pct
            take_profit = entry * base_target_pct

        return stop_loss, take_profit

    def _signal_to_action(self, direction: str) -> str:
        """Convert signal direction to trading action.

        Args:
            direction: Signal direction (long/short/neutral)

        Returns:
            Trading action (buy/sell/hold)
        """
        action_map = {
            "long": "buy",
            "short": "sell",
            "neutral": "hold",
        }

        return action_map.get(direction, "hold")
